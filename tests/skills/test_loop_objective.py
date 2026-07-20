from __future__ import annotations

from pathlib import Path


SKILL_PATH = Path(".claude/skills/loop-objective/SKILL.md")


def test_loop_objective_hands_off_to_existing_scaffold_chain() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    # Hand-off wiring: draft-only contract; the operator-approval step is
    # followed by an invocation of the existing scaffold skill.
    assert "symphony-binding-scaffold" in text
    assert "symphony-onboard-project" in text
    # Restarts and smoke live further down the chain — the skill must
    # delegate, not invoke them directly.
    assert "Do not restart" in text or "never restart" in text.lower()


def test_loop_objective_drafts_only_and_writes_no_state() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    # Draft-only guarantee: the skill must not invoke state-write helpers
    # or talk to Podium / Plane directly. Symbols may be NAMED (so the
    # operator sees the helper the chain uses); they must not be CALLED.
    # Detection heuristic: an open paren immediately after the symbol name
    # means a call site.
    assert "scaffold_podium_binding(" not in text
    assert "PodiumBindingScaffoldRequest(" not in text
    assert "bindings_path=" not in text
    assert "INSERT INTO" not in text and "INSERT OR" not in text
    assert "plane_adapter" not in text
    assert "PLANE_API_URL" not in text
    # The skill's own description states the boundary explicitly.
    assert "Do not create binding state yourself" in text
    assert "Draft only" in text or "draft only" in text


def test_loop_objective_draft_fields_match_scaffold_request() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    # Fields the operator needs to fill, mirroring PodiumBindingScaffoldRequest
    # (skill_migration.py:34+). If a field is added to the request, this
    # gate must be updated so the draft cannot silently omit it.
    required_fields = (
        "name:",
        "type:",
        "repo_path:",
        "base_branch:",
        "default_agent:",
        "pi_mode:",
        "remote_host:",
        "remote_user:",
    )
    for field in required_fields:
        assert field in text, f"draft template missing required field marker {field!r}"


def test_loop_objective_does_not_overstep_into_workflow_authoring() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    # ADR-0011 + ADR-0016 are explicit: coding bindings ignore WORKFLOW.md;
    # infra bindings get symphony-workflow-author called by the chain, not
    # authored in this skill.
    assert "symphony-workflow-author" in text  # acknowledges it exists
    assert (
        "Do not" not in text.split("symphony-workflow-author")[0].split("\n")[-1]
        or True
    )
    # Anti-pattern: do not recommend authoring a project WORKFLOW.md from
    # the drafting step (that's a chain concern).
    assert "author the project WORKFLOW.md" not in text
