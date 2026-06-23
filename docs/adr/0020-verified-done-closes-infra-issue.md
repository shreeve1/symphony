---
status: accepted
relates-to: ADR-0015 (patrol→Podium tracker adapter, auto-cure), ADR-0016 (INFRA_PREAMBLE renderer constant), ADR-0018 (patrol medium-risk window scheduling)
context: a remediated patrol finding parks in In Review forever instead of closing when the underlying condition is actually cleared
decided-with: James, 2026-06-23 (Issue #99, grill-me on "let infra bindings/homelab decide when issues close")
accepted: 2026-06-23 (implemented; see scheduler/__init__.py verified-close branch, config.ProjectBinding.auto_close_on_verified)
---

# A verified `done` verdict closes an infra issue instead of parking it in In Review

## Context

For an infra (non-coding) binding, the scheduler's terminal handler sends a
finished run to `in_review` for **both** a `review` and a `done` verdict
(`scheduler/__init__.py`, the `reason_code = "agent-marker-review" ...` block).
There is no agent path to `done`/closed at all. A patrol finding like
"aidev: reclaimable=9.0GB (>5GB)" therefore behaves like this: the operator (or
auto-remediation) clears the disk, the run finishes, and the issue lands in
`in_review` — never closing on its own. It only reaches `done` later, via the
homelab patrol worker's `record_pass` on a *subsequent* Temporal cycle, or the
symphony `blocked_reconciler` marker cure (and that only acts on `blocked`
issues). The operator sees the issue bounce back to In Review even though the
condition is resolved, and has to close it by hand.

## Decision

On an **opt-in** infra binding (`auto_close_on_verified: true` in `bindings.yml`),
a `done` verdict closes the issue directly (transition to `STATE_DONE`) instead
of parking it in In Review. The agent's `done` is the close signal because the
`INFRA_PREAMBLE` now instructs infra agents to **re-check the issue's own
measurable condition after acting** and emit `done` only when it is confirmed
cleared; otherwise emit `review`. Verification is the agent re-measuring the
real metric, not asserting success.

- The flag is **per-binding and defaults off** — this is the literal "infra
  bindings can decide" knob. `homelab` (patrols) opts in; every other binding
  keeps the universal In Review gate.
- `review` and unmarked clean runs are unchanged — still In Review.
- The flag is rejected at config-load for `type: coding` bindings (coding work
  always lands in In Review for operator merge; ADR-0014).
- The patrol's next cycle remains the backstop: if a `done` was wrong and the
  condition still holds, `record_failure` reopens the issue.

## Considered options

- **Trust any infra `done` globally (no flag).** Rejected: removes the human
  review gate for every infra finding, including ones an operator wants to eyeball.
- **A new "verified" marker distinct from `done`.** Rejected: the existing
  `done` vs `review` vocabulary already means "completed" vs "needs human", so the
  preamble can repurpose it without new contract surface.
- **Immediately re-trigger the homelab patrol check after remediation.** Rejected
  for v1: cross-repo trigger plumbing for no extra trust — the remediation agent
  just operated on the host and can re-measure in-run, eliminating both the In
  Review step and the wait-for-next-cycle lag.

## Consequences

- On flagged bindings, `done` now means "verified-resolved, will close" — a
  meaning shift agents must honor (enforced via the preamble, backstopped by the
  patrol reopen path).
- `symphony-host` must be restarted to pick up the renderer + scheduler change,
  and the live `bindings.yml` change, before the behavior takes effect.
