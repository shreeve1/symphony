# Preferred Skill is consumed on dispatch, not standing config

## Status

accepted

## Context

An Issue's `preferred_skill` drives a per-dispatch prompt directive ("First, invoke the `{skill}` skill…", `prompt_renderer.py:236-244`) — functionally a CLI `/skill` invocation. It was a *standing* column: once set, every subsequent dispatch re-invoked it, including the re-dispatch triggered by an Operator Reply. Operators hit a trap: create an issue under `dev-plan`, the agent plans and parks, the operator replies "build it", and the reply re-runs **still under `dev-plan`** because the dropdown silently carried the old value.

## Decision

Make `preferred_skill` **consume-on-dispatch**: the scheduler captures it into the Run's `skill_invoked`, then nulls the Issue's `preferred_skill` in the same dispatch — but only once the Run row is recorded. A blocked dispatch (bad model, skill missing from catalog, probe failure) or a deferred one (concurrency cap, cooldown, future schedule) leaves it intact. A skill-less dispatch is valid and renders as a plain agent continuation (no invoke directive). This mirrors CLI `/skill`: named once, invoked once; follow-up turns run skill-less unless the operator names a skill again.

This is deliberately **asymmetric** with the other Issue-level dispatch properties. `preferred_model` and `reasoning_effort` remain *standing* — they persist across every Run like a CLI session's model choice.

## Considered Options

- **Sticky skill (status quo).** Rejected: the carry-over trap above; the operator must remember to change or clear the dropdown before every reply.
- **Clear all three dropdowns (skill + model + effort) on dispatch.** Rejected: model/effort are session config, not per-turn verbs. Clearing them would silently drop every reply re-run to defaults, forcing constant re-selection.
- **Clear only on successful run completion.** Rejected: "success" is fuzzy (parked-for-review vs blocked vs done), and a crashed run would re-invoke the skill on retry — reintroducing the trap. "Consumed = Run row recorded" is the clean rule.

## Consequences

- No history is lost: `run.skill_invoked` (`scheduler.py:688`) preserves what ran; Run history still shows it. The flyout chip just empties.
- A run that crashes at startup loses the skill; re-picking is one click. Accepted as rare.
- The empty chip is the truth (server-side clear + live WS fanout), so it survives reload and stays consistent across clients.
