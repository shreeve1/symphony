# Patrol medium-risk updates self-schedule into the maintenance window

Status: proposed 2026-06-20

## Context

ADR-0015 routed Temporal patrols to the `homelab` Podium binding, and each finding
auto-dispatches a pi agent that remediates the live host. Safe, reversible fixes
(disk cleanup) apply immediately; **medium-risk scheduled changes** — package and
image updates, host reboots, docker prunes — correctly **block** instead, because
the runbooks forbid applying them outside an approved maintenance window and no
"current maintenance-window authorization" is present in an unattended run
(observed live 2026-06-20: issues 66 pve3, 71 ita-n8n, 74 aidev, etc.).

This is the agents behaving correctly, but it has no exit. The infra patrol runs
twice daily (`0 3,15` UTC = 8pm / 8am LA) — **never inside** the documented
12am–6am LA maintenance window — and a `blocked` issue does not re-dispatch on its
own (the ADR-0015 per-state contract makes a still-failing blocked finding
evidence-only). So medium-risk findings pile up in `blocked` across nearly every
host, every cycle, with no Podium-native way to grant the window and let them
apply. The detection cron is the wrong trigger for the apply step.

Podium already carries the machinery to fix this: a `scheduled_for TIMESTAMP`
column, `tracker_podium._scheduled_due()` dispatch gating, a `scheduled` label
derived from `scheduled_for`, the `Symphony-Schedule: not_before=…` comment
grammar (`schedule.py`), and `IssueCreate`/`IssuePatch` fields that already accept
`scheduled_for`. The working scheduler **already requires** a valid
`Symphony-Schedule` comment for any scheduled issue (`scheduler/__init__.py:1174`,
`"Scheduled ticket is missing a valid Symphony-Schedule comment."`) — the column
is the *flag*, the comment is the authoritative *time*.

## Decision

Medium-risk patrol findings **self-schedule into the next maintenance window and
apply unattended** when that window arrives, reusing the existing schedule
grammar rather than building a new gate. Operator chose hands-off over
operator-gated (2026-06-20 grill), explicitly reversing the agents' current
correct-blocking behavior for this class of finding.

Five parts:

1. **New `SYMPHONY_SCHEDULE: not_before=<iso>` output-contract marker** (symphony,
   `prompt_renderer.OUTPUT_CONTRACT` + scheduler parsing). A fourth agent outcome
   beside `SYMPHONY_RESULT: done|review|blocked`. The scheduler turns it into:
   post the `Symphony-Schedule: not_before=… reason=…` comment **and** set
   `scheduled_for`, leaving the issue in `todo`. **No new issue *state*** —
   `scheduled` is a flag (`scheduled_for` + `todo`), not a state — so it dodges the
   Podium `state` CHECK-constraint trap that broke Question Park (C-0211).

2. **The scheduled dispatch IS the authorization signal.** When the issue becomes
   due at window start, the scheduler already injects schedule context
   (`_with_schedule_context`, rendered `schedule_not_before`). INFRA_PREAMBLE
   (homelab side, the renderer constant from ADR-0016) gains one rule: *if you are
   dispatching from a Symphony schedule, you are in the approved maintenance
   window — apply the medium-risk update per runbook.* No separate window flag.

3. **INFRA_PREAMBLE flips block→schedule** for medium-risk scheduled updates: emit
   `SYMPHONY_SCHEDULE: not_before=<next 00:00 America/Los_Angeles>` instead of
   `SYMPHONY_RESULT: blocked`. High-risk findings still block. "Medium-risk" =
   whatever the runbooks already classify (incl. window-scheduled reboots, which
   repo policy already contemplates).

4. **Dedup must not clobber a scheduled issue** (the correctness landmine). The
   infra patrol re-detects the same pending update twice daily. When a finding's
   issue is already scheduled (`todo` + future `scheduled_for`), `record_failure`
   must be **evidence-only** — it must not reopen, reschedule, or reset
   `scheduled_for`, or the update slips to "next window" forever. Extend the
   ADR-0015 per-state contract to treat scheduled-pending like in-flight.

5. **First-class Schedule control in Podium UI** (infra bindings only):
   new-issue modal + issue flyout. Options *Next maintenance window* (default) /
   *Custom date-time* / *None*; writes `scheduled_for` **and** posts the
   `Symphony-Schedule:` comment through the existing API (satisfying the
   already-mandatory grammar gate). Gives the operator a one-click manual schedule
   on the same rails the agents use.

The **maintenance window** becomes a single backend config constant —
`00:00–06:00 America/Los_Angeles`, DST-aware via `zoneinfo` — single-sourced for
both the agent's "next window" computation and the UI's "Next maintenance window"
default (computed by a small backend helper, not duplicated in the frontend).
Advisory `not_after` = window end (06:00 LA) so the agent knows when the window
closes.

## Considered options

- **Operator one-click only (UI, no agent change).** Agents keep blocking; the new
  UI control schedules a blocked issue into the window with one click. Smallest,
  safest, zero agent-behavior change — but leaves a standing per-issue manual
  queue. Rejected as the end state; retained as the natural fallback if hands-off
  proves untrustworthy.
- **Dedicated window sweep** (new Temporal schedule at window start that reopens
  blocked patrol issues). Robust and cleanly decoupled, but a new scheduled job
  and a second scheduling mechanism alongside the grammar Podium already enforces.
  Rejected in favor of reusing `Symphony-Schedule`.
- **Re-time patrol crons into the window + inject authorization there.** No new
  job, but couples detection cadence to the window, loses the daytime detection
  pass, and can't defer a finding to a *later* window. Rejected.
- **Inject "you're in the window" into the normal patrol cycle.** Doesn't work:
  the detecting cron never runs in-window and blocked findings never re-fire.

## Consequences

- **Unattended medium-risk mutation of live infra.** Once INFRA_PREAMBLE flips,
  package/image updates and window-scheduled reboots apply across the fleet with
  no human in the loop, under the ADR-0015 blanket auto-approve (no carve-out).
  This is the hard-to-reverse blast-radius increase the operator accepted. The
  binding sandbox, runbook risk-classification, and the window boundary are the
  only guardrails. Recommend building the marker + in-window apply path and
  verifying it on one real finding **before** flipping INFRA_PREAMBLE — same code,
  one observation before the blast radius goes live.
- **Cross-repo:** symphony adds the `SYMPHONY_SCHEDULE` marker + scheduler
  handling + UI + window helper + the dedup-don't-clobber guard; homelab adds the
  INFRA_PREAMBLE block→schedule rule. Each commits to its own `main`.
- **Plane path unaffected** — this is Podium-scoped; Plane patrols keep blocking.
- Reuses, rather than reinvents, the dormant `scheduled_for` / `Symphony-Schedule`
  scheduling machinery that predates the patrol cutover.

## Related

- ADR-0015 — patrol→Podium tracker adapter (the per-state contract this extends)
- ADR-0016 — WORKFLOW.md retired; infra contract is the INFRA_PREAMBLE constant
- ADR-0005 — replace Plane with Podium
- `concepts/schedule-comment-grammar.md`, `concepts/scheduler-loop.md`
