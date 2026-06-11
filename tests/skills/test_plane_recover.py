from __future__ import annotations

from pathlib import Path


SKILL_PATH = Path(".claude/skills/symphony-plane-recover/SKILL.md")


def test_plane_recover_is_documented_as_retirement_only() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "Plane retirement tool only" in text
    assert "New bindings use `symphony-binding-scaffold`" in text
    assert "Never use this skill for new project onboarding" in text
