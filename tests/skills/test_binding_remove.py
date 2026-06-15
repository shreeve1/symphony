from __future__ import annotations

import sqlite3
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

skill_migration = cast(Any, import_module("skill_migration"))
PodiumBindingScaffoldRequest = skill_migration.PodiumBindingScaffoldRequest
scaffold_podium_binding = skill_migration.scaffold_podium_binding
remove_podium_binding = skill_migration.remove_podium_binding


SKILL_PATH = Path(".claude/skills/symphony-binding-remove/SKILL.md")


def _scaffold(tmp_path: Path, name: str = "demo") -> tuple[Path, Path]:
    db_path = tmp_path / "podium.db"
    bindings_path = tmp_path / "bindings.yml"
    scaffold_podium_binding(
        PodiumBindingScaffoldRequest(
            name=name,
            repo_path=tmp_path / "repo",
            base_branch="main",
        ),
        db_path=db_path,
        bindings_path=bindings_path,
    )
    return db_path, bindings_path


def test_remove_archives_db_row_and_drops_bindings_entry(tmp_path: Path) -> None:
    db_path, bindings_path = _scaffold(tmp_path)

    result = remove_podium_binding(
        "demo",
        db_path=db_path,
        bindings_path=bindings_path,
    )

    assert result.binding_name == "demo"
    assert result.removed_from_bindings_yml is True
    assert result.db_action == "archived"
    assert result.deleted_issue_count == 0
    assert result.deleted_run_count == 0

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT name, archived FROM binding WHERE name = 'demo'"
        ).fetchone()
    assert row == ("demo", 1)  # archived, history preserved

    raw = yaml.safe_load(bindings_path.read_text(encoding="utf-8"))
    assert raw["bindings"] == []


def test_remove_purge_deletes_binding_issues_and_runs(tmp_path: Path) -> None:
    db_path, bindings_path = _scaffold(tmp_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO issue(binding_name, title, description, state) VALUES (?, ?, ?, ?)",
            ("demo", "t", "d", "todo"),
        )
        issue_id = connection.execute(
            "SELECT id FROM issue WHERE binding_name = 'demo'"
        ).fetchone()[0]
        cursor = connection.execute(
            "INSERT INTO run(issue_id, state) VALUES (?, ?)", (issue_id, "queued")
        )
        # Realistic: a dispatched issue points back at its latest run, forming
        # the issue.latest_run_id <-> run.issue_id cycle that breaks a naive
        # delete order once foreign_keys is ON. Guards the purge FK regression.
        connection.execute(
            "UPDATE issue SET latest_run_id = ? WHERE id = ?",
            (cursor.lastrowid, issue_id),
        )
        connection.commit()

    result = remove_podium_binding(
        "demo",
        db_path=db_path,
        bindings_path=bindings_path,
        purge=True,
    )

    assert result.db_action == "deleted"
    assert result.deleted_issue_count == 1
    assert result.deleted_run_count == 1

    with sqlite3.connect(db_path) as connection:
        assert (
            connection.execute(
                "SELECT name FROM binding WHERE name = 'demo'"
            ).fetchone()
            is None
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM issue WHERE binding_name = 'demo'"
            ).fetchone()[0]
            == 0
        )
        # binding_settings is removed via ON DELETE CASCADE, not an explicit
        # delete; assert no orphan row survives the purge.
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM binding_settings WHERE binding_name = 'demo'"
            ).fetchone()[0]
            == 0
        )


def test_remove_unknown_binding_raises(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    bindings_path = tmp_path / "bindings.yml"

    with pytest.raises(ValueError, match="binding not found"):
        remove_podium_binding(
            "nope",
            db_path=db_path,
            bindings_path=bindings_path,
        )


def test_remove_binding_skill_is_not_plane_coupled() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "No Plane API calls" in text
    assert "plane_adapter" in text
    assert "PLANE_API_URL" not in text
    assert "api/v1/workspaces" not in text
