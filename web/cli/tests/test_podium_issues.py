from __future__ import annotations

import json
import sqlite3
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

podium_issues = cast(Any, import_module("web.cli.podium_issues"))
podium = cast(Any, import_module("web.cli.podium"))
schema = cast(Any, import_module("web.api.schema"))

create_plan_issues = podium_issues.create_plan_issues
resolve_binding_for_cwd = podium_issues.resolve_binding_for_cwd
PodiumIssuesError = podium_issues.PodiumIssuesError


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".kanban" / "issues").mkdir(parents=True)
    (repo / ".kanban" / "issues" / "999-do-not-touch.md").write_text(
        "sentinel", encoding="utf-8"
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
                        "type": "coding",
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


def _make_plan(tmp_path: Path) -> Path:
    path = tmp_path / "plan-slices.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "slices": [
                    {
                        "key": "api",
                        "title": "API slice",
                        "description": "Build the API path.",
                        "acceptance": ["API returns the new field"],
                        "verification": "uv run pytest tests/test_api.py -q",
                        "locks": ["web-api"],
                    },
                    {
                        "key": "ui",
                        "title": "UI slice",
                        "description": "Build the UI path.",
                        "acceptance": ["UI shows the new field"],
                        "verification": "pnpm test ui.spec.ts",
                        "blocked_by": ["api"],
                        "locks": ["web-frontend"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _init_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    with sqlite3.connect(db_path) as connection:
        connection.executescript(schema.SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name, sort_order) VALUES ('demo', 0)")
        connection.commit()
    return db_path


def _issue_rows(db_path: Path) -> list[tuple[Any, ...]]:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            """
            SELECT id, title, description, state, base_branch, preferred_agent,
                   blocked_by, locks
            FROM issue ORDER BY id
            """
        ).fetchall()


def test_resolve_binding_matches_repo(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    binding = resolve_binding_for_cwd(repo, bindings)
    assert binding["name"] == "demo"


def test_resolve_binding_no_match_raises(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    bindings = _make_bindings(tmp_path, repo)
    with pytest.raises(PodiumIssuesError, match="no podium binding matches"):
        resolve_binding_for_cwd(other, bindings)


def test_resolve_binding_rejects_non_podium_tracker(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo, tracker="plane")
    with pytest.raises(PodiumIssuesError):
        resolve_binding_for_cwd(repo, bindings)


def test_create_plan_issues_in_dependency_order_with_real_blockers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    plan = _make_plan(tmp_path)
    db_path = _init_db(tmp_path, monkeypatch)
    sentinel = repo / ".kanban" / "issues" / "999-do-not-touch.md"
    before = sentinel.read_text(encoding="utf-8")

    lines = create_plan_issues(repo, plan, bindings_path=bindings)
    assert lines[1:] == ["api 'API slice' -> podium #1", "ui 'UI slice' -> podium #2"]

    rows = _issue_rows(db_path)
    assert [r[1] for r in rows] == ["API slice", "UI slice"]
    assert json.loads(rows[0][6]) == []
    assert json.loads(rows[1][6]) == [1]
    assert json.loads(rows[0][7]) == ["web-api"]
    assert json.loads(rows[1][7]) == ["web-frontend"]
    assert "uv run pytest tests/test_api.py -q" in rows[0][2]
    assert rows[0][3:6] == ("todo", "main", "pi")
    assert sentinel.read_text(encoding="utf-8") == before


def test_dry_run_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    plan = _make_plan(tmp_path)
    db_path = _init_db(tmp_path, monkeypatch)

    lines = create_plan_issues(repo, plan, bindings_path=bindings, dry_run=True)
    assert any("dry-run" in line for line in lines)
    assert _issue_rows(db_path) == []


def test_unknown_dependency_is_rejected(tmp_path: Path) -> None:
    plan = tmp_path / "bad.yml"
    plan.write_text(
        yaml.safe_dump(
            {
                "slices": [
                    {
                        "key": "ui",
                        "title": "UI",
                        "acceptance": ["works"],
                        "verification": "uv run pytest -q",
                        "blocked_by": ["missing"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(PodiumIssuesError, match="unknown blocked_by"):
        podium_issues._load_plan_slices(plan)


def test_cli_create_from_plan_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    plan = _make_plan(tmp_path)
    _init_db(tmp_path, monkeypatch)
    assert (
        podium.main(
            [
                "issues",
                "create-from-plan",
                str(plan),
                "--cwd",
                str(repo),
                "--bindings",
                str(bindings),
                "--dry-run",
            ]
        )
        == 0
    )


def test_cli_no_binding_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    bindings = _make_bindings(tmp_path, repo)
    plan = _make_plan(tmp_path)
    _init_db(tmp_path, monkeypatch)
    rc = podium.main(
        [
            "issues",
            "create-from-plan",
            str(plan),
            "--cwd",
            str(other),
            "--bindings",
            str(bindings),
        ]
    )
    assert rc == 1
    assert "no podium binding matches" in capsys.readouterr().err


def test_cli_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    plan = _make_plan(tmp_path)
    _init_db(tmp_path, monkeypatch)
    create_plan_issues(repo, plan, bindings_path=bindings)

    assert podium.main(["issues", "list", "--binding", "demo"]) == 0
    out = capsys.readouterr().out
    assert "#1 demo todo blocked_by=[] locks=['web-api'] API slice" in out
    assert "#2 demo todo blocked_by=[1] locks=['web-frontend'] UI slice" in out
