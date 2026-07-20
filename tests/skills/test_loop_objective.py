from __future__ import annotations

from pathlib import Path


SKILL_PATH = Path(".claude/skills/loop-objective/SKILL.md")


def test_loop_objective_prompt_shape_mirrors_goal_objective() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    # The skill's contract fields are the loop-prompt analog of
    # goal-objective's goal fields. Keep them in parity so operators get
    # a familiar drafting shape.
    required_headings = (
        "## Loop objective",
        "## Stopping condition",
        "## Re-loop rule",
        "## Validation per iteration",
        "## Inputs to read first",
        "## Out of scope",
        "## Iteration strategy",
        "## Notes / Constraints",
    )
    for heading in required_headings:
        assert heading in text, f"draft template missing required heading {heading!r}"


def test_loop_objective_drafts_only_and_posts_no_issue() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    # Draft-only guarantee: the skill produces a prompt block the operator
    # pastes manually. It must NOT auto-post to Podium / invoke API calls
    # / smoke-helper machinery. Symbols may be NAMED (so the operator sees
    # the helpers that exist for OTHER skills); they must not be CALLED.
    # Detection heuristic: an open paren immediately after the symbol name
    # means a call site; the suffix `_for_status(` is a TestClient helper
    # shape that wouldn't appear outside a real network call.
    assert "client.post(" not in text
    assert "create_podium_smoke_issue(" not in text
    assert "requests.post(" not in text
    # The skill's own description states the boundary explicitly.
    assert "Do not create Podium state yourself" in text
    assert "Draft only" in text


def test_loop_objective_re_loop_rule_is_a_discrete_choice() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    # The four explicit re-loop forms (matches §3 of goal-objective's
    # "hold the draft to the same bar"). If a fifth form is added, the
    # test should be updated to gate it explicitly — silent re-loop-rule
    # ambiguity is one of the load-bearing gaps this skill closes.
    required_forms = (
        "one-shot",
        "on dependency",
        "patrol cadence",
        "operator-driven",
    )
    for form in required_forms:
        assert form in text, f"re-loop rule missing required form {form!r}"


def test_loop_objective_does_not_overstep_into_binding_creation() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    # Anti-pattern: this skill drafts a prompt, not a binding. References
    # to binding-creation machinery would signal drift back to the wrong
    # layer (the prior version of this skill did exactly that). The skill
    # may name a binding as the destination for the prompt; it must not
    # INVOKE binding-creation helpers or hand off into the onboarding
    # chain (which is binding creation + restart + smoke).
    for forbidden in (
        "symphony-binding-scaffold",
        "symphony-onboard-project",
        "symphony-restart",
        "scaffold_podium_binding",
        "PodiumBindingScaffoldRequest",
        "bindings_path=",
        "remote_host",
    ):
        assert forbidden not in text, (
            f"loop-prompt drafting skill should not reference {forbidden!r} "
            f"— that is binding-creation machinery, not prompt-drafting."
        )
