from __future__ import annotations

import sqlite3
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import yaml

skill_migration = cast(Any, import_module("skill_migration"))
PodiumBindingScaffoldRequest = skill_migration.PodiumBindingScaffoldRequest
scaffold_podium_binding = skill_migration.scaffold_podium_binding


SKILL_PATH = Path(".claude/skills/symphony-binding-scaffold/SKILL.md")


def test_binding_scaffold_creates_podium_db_row_and_bindings_entry(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    bindings_path = tmp_path / "bindings.yml"

    result = scaffold_podium_binding(
        PodiumBindingScaffoldRequest(
            name="demo",
            display_name="Demo",
            repo_path=tmp_path / "repo",
            base_branch="main",
        ),
        db_path=db_path,
        bindings_path=bindings_path,
    )

    assert result.binding_name == "demo"
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT name, display_name, archived FROM binding WHERE name = 'demo'"
        ).fetchone()
        settings = connection.execute(
            "SELECT context_compact_threshold_tokens FROM binding_settings WHERE binding_name = 'demo'"
        ).fetchone()
    assert row == ("demo", "Demo", 0)
    assert settings == (16000,)

    raw = yaml.safe_load(bindings_path.read_text(encoding="utf-8"))
    [binding] = raw["bindings"]
    assert binding["name"] == "demo"
    assert binding["tracker"] == "podium"
    assert binding["repo_path"] == str(tmp_path / "repo")
    assert binding["base_branch"] == "main"
    assert binding["plane_project_id"] == "demo"  # transitional config compatibility only


def test_binding_scaffold_skill_is_not_plane_coupled() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "No Plane API calls" in text
    assert "plane_adapter" in text
    assert "PLANE_API_URL" not in text
    assert "api/v1/workspaces" not in text
