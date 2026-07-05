from __future__ import annotations

import os
import shutil
import socket
import sqlite3
import subprocess
import sys
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import yaml

main = cast(Any, import_module("web.cli.podium")).main

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_SOURCE = REPO_ROOT / "web/api/tests/fixtures/skills"

HOST = socket.gethostname().split(".", 1)[0]


def _rows(db_path: Path) -> list[tuple[str, str, str, str, str]]:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            "SELECT name, description, source, host, binding_name FROM skill"
            " ORDER BY name"
        ).fetchall()


def _make_repo_with_skills(root: Path, fixture: Path) -> Path:
    """Build a repo whose .claude/skills is a copy of the fixture tree."""
    repo = root / "repo"
    shutil.copytree(fixture, repo / ".claude" / "skills")
    return repo


def _write_bindings(path: Path, repo: Path) -> Path:
    path.write_text(
        yaml.safe_dump(
            {"bindings": [{"name": "fixture", "repo_path": str(repo)}]},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_dry_run_command_lists_fixture_skills(tmp_path: Path) -> None:
    repo = _make_repo_with_skills(tmp_path, FIXTURE_SOURCE)
    bindings = _write_bindings(tmp_path / "bindings.yml", repo)
    empty_home = tmp_path / "home"
    empty_home.mkdir()

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "web.cli.podium",
            "skills",
            "refresh",
            "--dry-run",
            "--bindings",
            str(bindings),
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "HOME": str(empty_home)},
        capture_output=True,
        text=True,
        check=True,
    )

    names = [line.split("\t")[1] for line in result.stdout.splitlines() if "\t" in line]
    assert names == ["alpha", "bravo", "charlie"]


def test_set_password_writes_hash_to_stdout_only(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    result = subprocess.run(
        [sys.executable, "-m", "web.cli.podium", "set-password"],
        cwd=REPO_ROOT,
        input="secret\nsecret\n",
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.startswith("PODIUM_PASSWORD_HASH=$2")
    assert result.stderr == ""
    assert list(home.iterdir()) == []


def test_refresh_add_noop_change_and_remove(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    repo = _make_repo_with_skills(tmp_path, FIXTURE_SOURCE)
    skills_dir = repo / ".claude" / "skills"
    bindings = _write_bindings(tmp_path / "bindings.yml", repo)
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    # Empty HOME so no host-global skills are scanned; only the repo scope.
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))

    scope = f"[{HOST}/fixture]"

    assert main(["skills", "refresh", "--bindings", str(bindings)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"+ {scope} alpha",
        f"+ {scope} bravo",
        f"+ {scope} charlie",
    ]
    assert [(r[0], r[3], r[4]) for r in _rows(db_path)] == [
        ("alpha", HOST, "fixture"),
        ("bravo", HOST, "fixture"),
        ("charlie", HOST, "fixture"),
    ]

    # Second run is a no-op.
    assert main(["skills", "refresh", "--bindings", str(bindings)]) == 0
    assert capsys.readouterr().out == ""
    assert len(_rows(db_path)) == 3

    # A manual row (source='') in this scope must survive refresh.
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO skill(name, description, source, host, binding_name)"
            " VALUES (?, ?, ?, ?, ?)",
            ("manual", "Manual hand-seeded skill", "", HOST, "fixture"),
        )
        connection.commit()
    assert main(["skills", "refresh", "--bindings", str(bindings)]) == 0
    assert capsys.readouterr().out == ""
    assert any(r[0] == "manual" and r[2] == "" for r in _rows(db_path))

    # Change bravo, remove charlie.
    (skills_dir / "bravo/SKILL.md").write_text(
        "---\nname: bravo\ndescription: Bravo skill changed.\n---\n\n# Bravo\n",
        encoding="utf-8",
    )
    os.remove(skills_dir / "charlie/SKILL.md")

    assert main(["skills", "refresh", "--bindings", str(bindings)]) == 0
    assert capsys.readouterr().out.splitlines() == [f"- {scope} charlie"]
    remaining = {r[0]: r[1] for r in _rows(db_path)}
    assert remaining["bravo"] == "Bravo skill changed."
    assert "charlie" not in remaining
    assert "manual" in remaining
