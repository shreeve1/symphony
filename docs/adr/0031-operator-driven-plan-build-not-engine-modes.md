# Plan/Build is operator-driven via the issue body, not an engine-owned mode

## Status

accepted (2026-06-30). Implemented same day: Plan Mode / Build Mode sections removed from `INFRA_PREAMBLE` (`prompt_renderer.py`), the scheduler `mode == "build"` gate and its return-to-plan recovery removed (`scheduler/__init__.py`). Deployed by restarting `symphony-host.service`.

Supersedes the engine-owned plan/build-mode mechanics described in the Mode handling of earlier ADRs (notably the plan/build half of [ADR-0016](0016-workflow-md-retired-renderer-constant.md)'s `INFRA_PREAMBLE`).

## Context

Two findings about prompt bloat prompted a review of what Symphony injects into every infra dispatch. The `INFRA_PREAMBLE` constant carried ~30 lines of **Plan Mode** (rules 17–27) and **Build Mode** (rules 28–39) instructions — hardcoded host skill paths (`/home/james/.claude/skills/Development/...`), a Codex audit-loop directive, plan-file path conventions — rendered into *every* infra prompt regardless of whether the issue carried the `plan` or `build` label. A routine patrol finding paid the full cost of reading and ignoring that block.

Behind the preamble text sat a real scheduler mechanism: a `mode == "build" and not is_coding` gate that resolved mode from labels, hunted for a plan file under `plans/`, and on a miss either flipped the issue back to Plan mode (return-to-plan recovery) or — for skill-projected Podium issues, where the flip is a no-op and would bounce forever — blocked after a grace window. This was a fair amount of machinery serving a workflow the operator now wants to drive by hand.

The operator's decision: **stop having the engine own a plan-vs-build mode.** Plan and build are just instructions written in the issue body — "produce a plan," "execute the plan in `plans/foo.md`" — exactly like any other infra directive. The agent already reads the issue body as trusted operator instruction (ADR-0016 rule 11). An engine-enforced mode adds a label vocabulary, a plan-file-discovery contract, and a recovery state machine on top of something the operator can express in one sentence, with less control.

## Decision

Remove the engine's plan/build mode behavior:

- **Preamble** — strip the Plan Mode and Build Mode sections from `INFRA_PREAMBLE`. Infra issues receive only the portable harness contract (orientation, git ownership, execution, completion, output contract). The operator writes "plan this" or "build `plans/x.md`" in the issue body when that is what they want.
- **Scheduler** — delete the `mode == "build"` gate and the orphaned plan-path helpers (`_validated_fallback_plan_path`, `_expected_plan_path`, `_validate_issue_plan_path`, `_plan_stem_matches_issue`, `_issue_slug`) and constants (`BUILD_PLAN_MISSING_GRACE_ATTEMPTS`, `_BUILD_PLAN_RETURN_MARKER`). A `dev-build` issue with no plan now just dispatches; the agent handles a missing plan in-conversation like any other instruction.

## What deliberately stays (surgical, not a full rip-out)

`_resolve_mode` and the `mode` field on `TickResult` are kept — they degrade to logging-only and removing them is pure churn. `mode_for_skill` / `SKILL_TO_MODE` and the Podium `preferred_skill`→`plan`/`build` label projection in `tracker_podium.py` stay: they are now **inert** (labels are produced but no gate acts on them), and the dormant Plane `MODE_PLAN`/`MODE_BUILD` contract enums and the `dev-plan`/`dev-build` skill catalog rows remain as ordinary selectable skills. None of these reach the prompt or change behavior. This keeps the change reversible if label-driven modes are ever wanted back.

## Consequences

- The operator has direct, sentence-level control over plan vs build; there is no label to set and no plan-file-location contract to satisfy.
- Lost: automatic return-to-plan recovery when a `build` issue has no plan. Acceptable — the agent now reports the missing plan in its turn, and the operator decides.
- Inert plan/build label vocabulary remains visible in the codebase (skills, enums, label projection). A future cleanup can remove it if the dormancy proves permanent; flagged, not done here.
