"""Transitional Skill-to-Mode projection for Podium dispatch.

Podium stores the operator's work-shape choice as ``preferred_skill``. The
legacy renderer still emits ``{{issue.mode}}`` for existing WORKFLOW.md
contracts, so this module is the single source of truth for projecting known
Skills back to legacy Mode values during migration.
"""

from __future__ import annotations

from typing import Literal

Mode = Literal["plan", "build", "execute"]

SKILL_TO_MODE: dict[str, Mode] = {
    "/dev-plan": "plan",
    "/dev-build": "build",
    "/diagnose": "execute",
    "/code-review": "execute",
}


def mode_for_skill(preferred_skill: str | None) -> Mode:
    """Return the legacy renderer Mode for a Podium preferred Skill."""

    if preferred_skill is None:
        return "execute"
    return SKILL_TO_MODE.get(preferred_skill, "execute")
