from __future__ import annotations

from pathlib import Path


SKILL_PATH = Path(".claude/skills/symphony-onboard-project/SKILL.md")


def test_onboard_project_uses_migrated_podium_subskills() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "symphony-binding-scaffold" in text
    # symphony-workflow-author retired (ADR-0016) — no longer referenced.
    assert "symphony-restart" in text
    assert "symphony-binding-smoke" in text
    assert "Do not call `symphony-project-scaffold`" in text
    assert "Do not call `symphony-plane-recover`" in text
