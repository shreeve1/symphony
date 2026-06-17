from __future__ import annotations

import sqlite3
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

podium_issues = cast(Any, import_module("web.cli.podium_issues"))
podium = cast(Any, import_module("web.cli.podium"))
schema = cast(Any, import_module("web.api.schema"))

import_kanban_issues = podium_issues.import_kanban_issues
resolve_binding_for_cwd = podium_issues.resolve_binding_for_cwd
parse_kanban_issue = podium_issues.parse_kanban_issue
scan_pending = podium_issues.scan_pending
PodiumIssuesError = podium_issues.PodiumIssuesError


ISSUE_TEMPLATE = """---
id: {kid_padded}
title: {title}
status: pending
blocked_by: {blocked_by}
parent: null
priority: 0
created: 2026-06-16
---

## What to build

Slice {kid}.

## Blocked by

{blocked_note}
"""


def _make_repo(tmp_path: Path, *issues: tuple[int, str]) -> Path:
    repo = tmp_path / "repo"
    kanban = repo / ".kanban" / "issues"
    kanban.mkdir(parents=True)
    for kid, title in issues:
        slug = title.lower().replace(" ", "-")
        (kanban / f"{kid:03d}-{slug}.md").write_text(
            ISSUE_TEMPLATE.format(
                kid=kid,
                kid_padded=f"{kid:03d}",
                title=title,
                blocked_by="[]",
                blocked_note="None - can start immediately",
            ),
            encoding="utf-8",
        )
    return repo


def _make_bindings(tmp_path: Path, repo: Path, *, tracker: str = "podium") -> Path:
    path = tmp_path / "bindings.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "bindings": [
                    {
                        "name": "demo",
                        "tracker": tracker,
                        "type": "infra",
                        "repo_path": str(repo),
                        "base_branch": "main",
                        "default_agent": "pi",
                        "approval": {"enabled": False},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _init_db(tmp_path: Path, monkeypatch) -> Path:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    with sqlite3.connect(db_path) as connection:
        connection.executescript(schema.SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name, sort_order) VALUES ('demo', 0)")
        connection.commit()
    return db_path


def _issue_rows(db_path: Path) -> list[tuple[Any, ...]]:
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        return connection.execute(
            "SELECT id, binding_name, title, state, base_branch, preferred_agent,"
            " priority FROM issue ORDER BY id"
        ).fetchall()


def test_resolve_binding_matches_repo(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, (1, "one"))
    bindings = _make_bindings(tmp_path, repo)
    binding = resolve_binding_for_cwd(repo, bindings)
    assert binding["name"] == "demo"


def test_resolve_binding_no_match_raises(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, (1, "one"))
    other = tmp_path / "elsewhere"
    other.mkdir()
    bindings = _make_bindings(tmp_path, repo)
    with pytest.raises(PodiumIssuesError, match="no podium binding matches"):
        resolve_binding_for_cwd(other, bindings)


def test_resolve_binding_rejects_non_podium_tracker(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, (1, "one"))
    bindings = _make_bindings(tmp_path, repo, tracker="plane")
    with pytest.raises(PodiumIssuesError):
        resolve_binding_for_cwd(repo, bindings)


def test_parse_extracts_frontmatter_and_body(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, (7, "lucky slice"))
    issue = parse_kanban_issue(repo / ".kanban/issues/007-lucky-slice.md")
    assert issue.kid == 7
    assert issue.title == "lucky slice"
    assert "Slice 7." in issue.body
    assert issue.podium_issue_id is None


def test_parse_zero_padded_id_is_decimal_not_octal(tmp_path: Path) -> None:
    # ``id: 060`` is octal under YAML 1.1 (-> 48); the parser must read it as
    # decimal 60 to match the filename and Ralph's ``grep "^id: NNN$"`` lookup.
    repo = _make_repo(tmp_path, (60, "octal trap"))
    issue = parse_kanban_issue(repo / ".kanban/issues/060-octal-trap.md")
    assert issue.kid == 60


def test_import_inserts_in_ascending_id_order(tmp_path: Path, monkeypatch) -> None:
    repo = _make_repo(tmp_path, (3, "third"), (1, "first"), (2, "second"))
    bindings = _make_bindings(tmp_path, repo)
    db_path = _init_db(tmp_path, monkeypatch)

    lines = import_kanban_issues(repo, bindings_path=bindings)
    assert any("podium #" in line for line in lines)

    rows = _issue_rows(db_path)
    # DB ids ascend with insertion; titles must follow ascending kanban id.
    titles = [r[2] for r in rows]
    assert titles == ["[k#1] first", "[k#2] second", "[k#3] third"]
    for row in rows:
        assert row[3] == "todo"
        assert row[4] == "main"
        assert row[5] == "pi"
        assert row[6] is None


def test_import_writes_back_marker_and_is_idempotent(
    tmp_path: Path, monkeypatch
) -> None:
    repo = _make_repo(tmp_path, (1, "first"))
    bindings = _make_bindings(tmp_path, repo)
    db_path = _init_db(tmp_path, monkeypatch)

    import_kanban_issues(repo, bindings_path=bindings)
    text = (repo / ".kanban/issues/001-first.md").read_text(encoding="utf-8")
    front = yaml.safe_load(text.split("---", 2)[1])
    assert front["podium_issue_id"] == 1
    assert front["podium_binding"] == "demo"
    assert "Slice 1." in text  # body preserved

    # Second run: marker present -> nothing new inserted.
    lines = import_kanban_issues(repo, bindings_path=bindings)
    assert "pending=0" in lines[0]
    assert len(_issue_rows(db_path)) == 1


def test_dry_run_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    repo = _make_repo(tmp_path, (1, "first"))
    bindings = _make_bindings(tmp_path, repo)
    db_path = _init_db(tmp_path, monkeypatch)
    before = (repo / ".kanban/issues/001-first.md").read_text(encoding="utf-8")

    lines = import_kanban_issues(repo, bindings_path=bindings, dry_run=True)
    assert any("dry-run" in line for line in lines)
    assert _issue_rows(db_path) == []
    assert (repo / ".kanban/issues/001-first.md").read_text(encoding="utf-8") == before


def test_cli_import_kanban_dry_run(tmp_path: Path, monkeypatch) -> None:
    repo = _make_repo(tmp_path, (1, "first"))
    bindings = _make_bindings(tmp_path, repo)
    _init_db(tmp_path, monkeypatch)
    assert (
        podium.main(
            [
                "issues",
                "import-kanban",
                "--cwd",
                str(repo),
                "--bindings",
                str(bindings),
                "--dry-run",
            ]
        )
        == 0
    )


def test_cli_import_kanban_no_binding_returns_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo = _make_repo(tmp_path, (1, "first"))
    other = tmp_path / "elsewhere"
    other.mkdir()
    bindings = _make_bindings(tmp_path, repo)
    _init_db(tmp_path, monkeypatch)
    rc = podium.main(
        ["issues", "import-kanban", "--cwd", str(other), "--bindings", str(bindings)]
    )
    assert rc == 1
    assert "no podium binding matches" in capsys.readouterr().err
