from __future__ import annotations

from pathlib import Path


SKILL_PATH = Path(".claude/skills/symphony-workflow-author/SKILL.md")


def test_workflow_author_documents_tracker_agnostic_behavior() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "tracker-agnostic" in text
    assert "It does not write Podium or Plane" in text
    assert "Never write a Workflow for an unbound repo" in text
    assert "Never restart Symphony or file smoke Issues" in text
    assert "checkpointed-exploration" in text
    assert "one bounded exploration step per Run" in text
