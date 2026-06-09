---
title: pi-swap review specs (4 review-PRD artifacts)
type: analysis
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - wiki/raw/spec-adversarially-review-this-implementation-plan-fo.md
  - wiki/raw/spec-review-brief-review-type-build-review-project-co.md
  - wiki/raw/spec-review-the-current-code-changes-staged-unstaged-.md
  - wiki/raw/spec-the-plan-at-plans-symphony-pi-executor-swap-md-h.md
confidence: medium
tags: [review, PRD, adversarial-review, codex, dev-review, audit, pi-swap]
---

# pi-swap review specs — 4 review-PRD artifacts

`artifacts/specs/<truncated-prompt>/PRD.md` files capture the review briefs that drove the pi-executor-swap audit loop. Each is a self-contained reviewer PRD: requested outcome, current state, ideal-state criteria, scope, assumptions, risks, approach. They are not plans or code — they are the instructions handed to a reviewer (Claude / Codex / dev-review-claude) for a specific audit round.

## The four briefs

### 1. Adversarial Plan Review (round 1, plan-level)

[source: wiki/raw/spec-adversarially-review-this-implementation-plan-fo.md]

- **Target**: `plans/symphony-pi-executor-swap.md`
- **Focus**: execution risk, feasibility, duplication, missing edge cases, dependency fit, test strategy
- **Ground rule**: every finding backed by actual repo evidence; required severity format exact; final line `END_OF_FINDINGS`
- **Reviewer**: presumably a `/dev-review-claude` adversarial pass

### 2. Build Review (post-implementation diff)

[source: wiki/raw/spec-review-brief-review-type-build-review-project-co.md]

- **Target**: uncommitted build diff in `/home/james/plane/symphony` (pre-move path)
- **Focus**: correctness, plan compliance, safety regressions, test completeness, stale runtime references, untracked-file risks
- **Reported validation context**: `uv run pytest -q` → 249 passed; `py_compile *.py` → exit 0; source stale-reference search for `opencode|OPENCODE|OpenCode|CLIPROXY` → no matches
- **Ideal-state checklist** captures the exact safety contract the swap had to preserve:
  - direct pi dispatch replaces opencode without losing prompt rendering, Plane state transitions, `plane` PATH shim, scheduler safety checks
  - startup-only pi verification catches missing binary, unsupported provider/model/auth silent failures
  - `run_agent` handles blank success output, timeouts, subprocess errors, env injection, cwd, output capture safely
  - scheduler comments, redaction, state transitions, pre-dirty handling, permission/approval gates remain safe and don't leak secrets
  - omission of stdout from comments does not remove required marker or workflow signals
  - included Plane poller dirty changes preserve mixed-state pagination behavior

### 3. Generic Code-Changes Review

[source: wiki/raw/spec-review-the-current-code-changes-staged-unstaged-.md]

- **Target**: all staged/unstaged/untracked changes
- **Output shape**: prioritized JSON review with discrete bug/regression findings only; no fixes; no production code edits during review; no speculation; PRD artifact itself excluded from findings
- **Use**: general-purpose review wrapper, not pi-swap-specific despite living in this artifacts dir

### 4. Round 3 Plan Review (post-revisions)

[source: wiki/raw/spec-the-plan-at-plans-symphony-pi-executor-swap-md-h.md]

- **Target**: the latest revised `plans/symphony-pi-executor-swap.md`
- **Focus**: for each round-2 finding, status = `ADDRESSED` / `NOT_ADDRESSED` / `PARTIALLY_ADDRESSED` with a concise reason; new revision-caused risks listed separately; evidence in current plan + repo files
- **Round-2 themes called out**: stale OpenCode references, startup probe cwd/context parity, verifier insertion order before transport construction, live env documentation for pi variables

## Why this matters in the wiki

These artifacts document the **audit discipline** that produced the pi-swap landing — at least three review rounds (round 1 adversarial, round 2 implicit, round 3 explicit) plus a build-diff review post-implementation. The Symphony team treats orchestration changes as expensive enough to warrant multi-round adversarial review with a fixed output format and explicit evidence-grounding rules.

## Cross-references

- The build-review brief's "uv run pytest -q → 249 passed" is the validation handed to the reviewer, not a claim that 249 is current; today's count may differ. Verify with `python3 -m pytest -q` if asked.
- "Pre-dirty handling" and "permission/approval gates" are scheduler-level concepts whose state at swap time was preserved; current state should be re-checked against `scheduler.py` if these areas are touched.
- Round 3 brief implies a `findings` JSON schema common to the audit pipeline; format is not captured in these PRDs — would need to be ingested from a sample reviewer output.

## Notes

- All 4 PRD files live under `artifacts/specs/<truncated-67-char-prompt-slug>/PRD.md` — directory names are auto-truncated review prompts. Future review briefs likely follow the same shape.
- The PRD scaffolding (Requested outcome / Current state / Ideal state / Scope / Assumptions / Risks / Approach) is a reusable template worth recognizing in future ingest passes.

## Related

- [Brainstorm — pi-executor swap](brainstorm-pi-swap.md)
- [Plan history — symphony-pi-executor-swap](symphony-plan-history.md#symphony-pi-executor-swap)
