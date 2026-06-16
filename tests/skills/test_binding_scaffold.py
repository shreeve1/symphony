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


def test_binding_scaffold_creates_podium_db_row_and_bindings_entry(
    tmp_path: Path,
) -> None:
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
    assert (
        binding["plane_project_id"] == "demo"
    )  # transitional config compatibility only
    assert (
        binding["pi_mode"] == "rpc"
    )  # RPC is the default for new pi bindings (ADR-0010)


def test_binding_scaffold_pi_mode_one_shot_and_claude_omits_it(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    bindings_path = tmp_path / "bindings.yml"

    scaffold_podium_binding(
        PodiumBindingScaffoldRequest(
            name="legacy",
            repo_path=tmp_path / "repo-a",
            base_branch="main",
            pi_mode="one-shot",
        ),
        db_path=db_path,
        bindings_path=bindings_path,
    )
    scaffold_podium_binding(
        PodiumBindingScaffoldRequest(
            name="cl",
            repo_path=tmp_path / "repo-b",
            base_branch="main",
            default_agent="claude",
        ),
        db_path=db_path,
        bindings_path=bindings_path,
    )

    raw = yaml.safe_load(bindings_path.read_text(encoding="utf-8"))
    by_name = {b["name"]: b for b in raw["bindings"]}
    assert by_name["legacy"]["pi_mode"] == "one-shot"  # rollback path selectable
    assert "pi_mode" not in by_name["cl"]  # claude bindings carry no pi_mode


def test_binding_scaffold_writes_remote_block(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    bindings_path = tmp_path / "bindings.yml"

    scaffold_podium_binding(
        PodiumBindingScaffoldRequest(
            name="n8n",
            repo_path=Path("/home/itadmin/itastack"),
            base_branch="main",
            pi_mode="one-shot",
            remote_host="100.95.224.218",
            remote_user="itadmin",
        ),
        db_path=db_path,
        bindings_path=bindings_path,
    )

    raw = yaml.safe_load(bindings_path.read_text(encoding="utf-8"))
    [binding] = raw["bindings"]
    assert binding["remote"] == {"host": "100.95.224.218", "user": "itadmin"}
    assert "identity" not in binding["remote"]


def test_binding_scaffold_remote_requires_one_shot_pi_coding(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    bindings_path = tmp_path / "bindings.yml"

    base = dict(
        name="bad",
        repo_path=Path("/home/itadmin/itastack"),
        base_branch="main",
        remote_host="100.95.224.218",
        remote_user="itadmin",
    )

    # rpc rejected for remote (v1 requires one-shot)
    try:
        scaffold_podium_binding(
            PodiumBindingScaffoldRequest(**base, pi_mode="rpc"),
            db_path=db_path,
            bindings_path=bindings_path,
        )
    except ValueError as exc:
        assert "one-shot" in str(exc)
    else:
        raise AssertionError("expected ValueError for remote pi_mode=rpc")

    # host without user rejected
    try:
        scaffold_podium_binding(
            PodiumBindingScaffoldRequest(
                name="bad2",
                repo_path=Path("/home/itadmin/itastack"),
                base_branch="main",
                pi_mode="one-shot",
                remote_host="100.95.224.218",
            ),
            db_path=db_path,
            bindings_path=bindings_path,
        )
    except ValueError as exc:
        assert "remote_user" in str(exc)
    else:
        raise AssertionError("expected ValueError for remote_host without remote_user")


def test_binding_scaffold_skill_is_not_plane_coupled() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "No Plane API calls" in text
    assert "plane_adapter" in text
    assert "PLANE_API_URL" not in text
    assert "api/v1/workspaces" not in text
