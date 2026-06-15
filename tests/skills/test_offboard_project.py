from __future__ import annotations

from pathlib import Path


SKILL_PATH = Path(".claude/skills/symphony-offboard-project/SKILL.md")


def test_offboard_project_uses_migrated_podium_subskills() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "symphony-bindings-status" in text
    assert "symphony-binding-remove" in text
    assert "symphony-restart" in text
    assert "Do not call `symphony-plane-recover`" in text


def test_offboard_project_defaults_to_archive_not_purge() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "Default to archive" in text
    assert "purge" in text
    assert "PLANE_API_URL" not in text
    assert "api/v1/workspaces" not in text
