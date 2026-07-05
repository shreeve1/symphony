"""ADR-0033 per-host/per-binding skill sync tests."""

from __future__ import annotations

import sqlite3
from importlib import import_module
from pathlib import Path
from typing import Any, cast

_skills = cast(Any, import_module("web.cli.podium_skills"))

SKILL_MD = """---
name: {name}
description: {desc}
---

body
"""


def _write_skill(root: Path, name: str, desc: str) -> None:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(SKILL_MD.format(name=name, desc=desc), encoding="utf-8")


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _skills.ensure_schema(conn)
    return conn


def test_local_sync_scopes_global_and_project(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".claude" / "skills").mkdir(parents=True)
    _write_skill(home / ".claude" / "skills", "tdd", "global tdd")

    repo = tmp_path / "repo"
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_skill(repo / ".claude" / "skills", "proj-only", "project skill")

    # Point the global scan at our fake home via monkeypatched expanduser is
    # heavy; instead pass an absolute repo and a HOME override.
    import os

    old_home = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        conn = _fresh_db()
        bindings = [{"name": "symphony", "repo_path": str(repo)}]
        changes = _skills.sync_skills(bindings, connection=conn, local_hostname="aidev")
    finally:
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home

    rows = {
        (r["name"], r["host"], r["binding_name"])
        for r in conn.execute("SELECT name, host, binding_name FROM skill")
    }
    assert ("tdd", "aidev", None) in rows
    assert ("proj-only", "aidev", "symphony") in rows
    assert any(c.startswith("+") for c in changes)


def test_sync_replaces_scope_and_protects_manual_rows(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_skill(repo / ".claude" / "skills", "keep", "kept")

    conn = _fresh_db()
    # Pre-existing file-backed row in this scope that is no longer on disk, plus
    # a manual row (source='') that must survive.
    conn.execute(
        "INSERT INTO skill(name, description, source, host, binding_name)"
        " VALUES (?, ?, ?, ?, ?)",
        ("stale", "", "/old/SKILL.md", "aidev", "symphony"),
    )
    conn.execute(
        "INSERT INTO skill(name, description, source, host, binding_name)"
        " VALUES (?, ?, ?, ?, ?)",
        ("manual", "hand made", "", "aidev", "symphony"),
    )
    conn.commit()

    import os

    old_home = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path / "no-home")
    try:
        bindings = [{"name": "symphony", "repo_path": str(repo)}]
        _skills.sync_skills(bindings, connection=conn, local_hostname="aidev")
    finally:
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home

    names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM skill WHERE host = 'aidev' AND binding_name = 'symphony'"
        )
    }
    assert "keep" in names
    assert "manual" in names  # source='' protected
    assert "stale" not in names  # file-backed, absent from scan → deleted


def test_remote_scope_scanned_over_ssh(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_ssh(args, **kwargs):
        captured["args"] = args
        marker = _skills._REMOTE_FILE_MARKER
        stdout = (
            f"{marker} /home/itadmin/itastack/.claude/skills/itastack-deploy/SKILL.md\n"
            "---\n"
            "name: itastack-deploy\n"
            "description: itastack only\n"
            "---\n"
            "body\n"
        )
        return type("R", (), {"returncode": 0, "stdout": stdout, "stderr": ""})()

    conn = _fresh_db()
    bindings = [
        {
            "name": "n8n",
            "repo_path": "/home/itadmin/itastack",
            "remote": {"host": "n8n", "user": "itadmin"},
        }
    ]
    _skills.sync_skills(
        bindings, connection=conn, local_hostname="aidev", ssh_run=fake_ssh
    )

    rows = {
        (r["name"], r["host"], r["binding_name"])
        for r in conn.execute("SELECT name, host, binding_name FROM skill")
    }
    assert ("itastack-deploy", "n8n", "n8n") in rows
    assert any("n8n" in str(a) for a in captured["args"])
    # -L so a symlinked ~/.claude/skills (dotfiles) is followed on the remote.
    assert any("find -L" in str(a) for a in captured["args"])


def test_unreachable_host_is_best_effort(tmp_path: Path) -> None:
    def failing_ssh(args, **kwargs):
        return type("R", (), {"returncode": 255, "stdout": "", "stderr": "no route"})()

    conn = _fresh_db()
    # Pre-existing remote row must survive an unreachable scan (scope untouched).
    conn.execute(
        "INSERT INTO skill(name, description, source, host, binding_name)"
        " VALUES (?, ?, ?, ?, ?)",
        ("stale-remote", "", "/r/SKILL.md", "n8n", "n8n"),
    )
    conn.commit()

    bindings = [
        {
            "name": "n8n",
            "repo_path": "/home/itadmin/itastack",
            "remote": {"host": "n8n", "user": "itadmin"},
        }
    ]
    # Must not raise despite SSH failure.
    _skills.sync_skills(
        bindings, connection=conn, local_hostname="aidev", ssh_run=failing_ssh
    )

    names = {r["name"] for r in conn.execute("SELECT name FROM skill")}
    assert "stale-remote" in names
