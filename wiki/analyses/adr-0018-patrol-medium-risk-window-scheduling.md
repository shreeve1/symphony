---
title: ADR-0018 — Patrol medium-risk updates self-schedule into the maintenance window
type: analysis
status: promoted
created: 2026-06-20
updated: 2026-06-21
last_event: 2026-06-21 #95 scheduler terminal schedule handler landed
sources:
  - docs/adr/0018-patrol-medium-risk-window-scheduling.md
  - wiki/raw/sessions/2026-06-20-patrol-window-scheduling-grill.md
  - prompt_renderer.py
  - scheduler/__init__.py
  - scheduler/markers.py
  - schedule.py
  - tracker_podium.py
  - web/api/schema.py
  - web/api/main.py
  - automation/homelab-stack/src/homelab_worker/patrol_config.py
  - .kanban/issues/093-schedule-foundations-next-window-prefer-last.md
  - .kanban/issues/094-symphony-schedule-marker.md
  - .kanban/issues/095-scheduler-terminal-schedule-handler.md
confidence: high
tags: [adr, patrol, podium, scheduling, maintenance-window, symphony-schedule, output-contract, infra-preamble, blast-radius, temporal, homelab, cross-repo, proposed]
---

# ADR-0018 — Patrol medium-risk updates self-schedule into the maintenance window

`proposed` 2026-06-20. Outcome of a `/grill-me` review of what's outstanding
between Temporal patrols and Podium after the ADR-0015 cutover. **Partially built:** #93 landed the shared maintenance-window helper, `next_window` parser resolution, and Podium latest-control-line selection; #94 landed the `SYMPHONY_SCHEDULE` stdout parser plus output-contract/INFRA_PREAMBLE mechanism wording; #95 landed scheduler terminal handling for valid/malformed markers. Schedule-authorization policy, dedup guard, and UI control remain unbuilt. Cross-repo (symphony + homelab). [source: .kanban/issues/093-schedule-foundations-next-window-prefer-last.md] [source: .kanban/issues/094-symphony-schedule-marker.md] [source: .kanban/issues/095-scheduler-terminal-schedule-handler.md] [source: schedule.py#414-446] [source: scheduler/markers.py#70-91] [source: scheduler/__init__.py#1795-1861]

## Problem

ADR-0015 routed patrols to the `homelab` Podium binding; each finding
auto-dispatches a pi agent that remediates the live host. Safe fixes apply
immediately, but **medium-risk scheduled changes** (package/image updates,
reboots, docker prunes) correctly **block** — runbooks forbid applying them
outside an approved maintenance window, and an unattended run has no
"current maintenance-window authorization." Live 2026-06-20: issues 66/71/74 et
al. blocked across nearly every host.

The block has no exit. Infra patrol runs `0 3,15` UTC = **8pm/8am LA — never
inside** the 12am–6am LA window, and a blocked finding is evidence-only on
re-detection (ADR-0015 per-state contract), so it never re-fires. The detection
cron is the wrong trigger for the apply step. [source:
wiki/raw/sessions/2026-06-20-patrol-window-scheduling-grill.md]

Podium already carries the (dormant) fix: `scheduled_for` column,
`_scheduled_due()` gate, the `scheduled` derived label, the `Symphony-Schedule:`
comment grammar, and `IssueCreate/IssuePatch` `scheduled_for` fields. The
scheduler **already requires** a `Symphony-Schedule` comment for any scheduled
issue (`scheduler/__init__.py:1174`) — column = flag, comment = authoritative time.

## Decision

Medium-risk patrol findings **self-schedule into the next maintenance window and
apply unattended** when it arrives, reusing the schedule grammar rather than a new
gate. Operator chose **hands-off** over operator-gated (grill Q3), explicitly
reversing the agents' current correct-blocking behavior. Five parts:

1. **`SYMPHONY_SCHEDULE: not_before=<next_window|iso8601-with-offset> reason="..."` output-contract marker** (symphony) — a
   4th agent outcome beside `SYMPHONY_RESULT`. #94 implemented parsing and prompt-contract wording; #95 makes the scheduler post the
   `Symphony-Schedule:` comment, add the scheduled label/flag, and return the issue to `todo` while finishing the Run with `verdict=None`. **No
   new issue state** → avoids the C-0211 Podium `state` CHECK-constraint trap. [source: scheduler/__init__.py#1795-1861]
2. **Scheduled dispatch = authorization.** At window start the scheduler injects
   schedule context (`_with_schedule_context`); INFRA_PREAMBLE gains one rule:
   "dispatching from a Symphony schedule ⇒ you are in the approved window, apply."
3. **INFRA_PREAMBLE flips block→schedule** for medium-risk scheduled updates
   (high-risk still blocks). "Medium-risk" = whatever the runbooks classify, incl.
   window-scheduled reboots (repo policy already contemplates).
4. **Dedup must not clobber a scheduled issue** (correctness landmine):
   `record_failure` on a `todo`+future-`scheduled_for` issue must be evidence-only,
   or the update slips to "next window" forever. Extends the ADR-0015 per-state
   contract — treat scheduled-pending like in-flight.
5. **First-class Schedule control in Podium UI** (infra bindings only; new-issue
   modal + flyout). *Next maintenance window* (default) / *Custom date-time* /
   *None*; writes `scheduled_for` AND posts the `Symphony-Schedule:` comment via
   the existing API (satisfying the mandatory grammar gate).

Maintenance window = one backend config constant, `00:00–06:00
America/Los_Angeles`, DST-aware (`zoneinfo`), single-sourced for both the agent's
"next window" computation and the UI "Next maintenance window" default (computed
by a backend helper). Advisory `not_after` = 06:00 LA. #93 moved the constants and helper into `schedule.py`; the scheduler's label-only fallback now delegates to it while preserving the `(not_before, not_after)` pair. [source: schedule.py#127-129] [source: schedule.py#414-431] [source: scheduler/__init__.py#2654-2662]

## Rejected alternatives

- **Operator one-click only (UI, no agent change)** — smallest/safest but leaves a
  standing manual queue; retained as the fallback if hands-off proves untrusted.
- **Dedicated window sweep (new Temporal schedule)** — robust but a second
  scheduling mechanism alongside the grammar Podium already enforces.
- **Re-time patrol crons into the window** — couples detection cadence to the
  window, loses the daytime pass, can't defer to a later window.
- **Inject "you're in the window" into the normal cycle** — the detecting cron
  never runs in-window and blocked findings never re-fire.

## Consequences

- **Unattended medium-risk mutation of live infra** — package/image updates +
  window-scheduled reboots apply fleet-wide with no human in the loop, under the
  ADR-0015 blanket auto-approve. The hard-to-reverse blast-radius increase the
  operator accepted; sandbox + runbook risk-classification + window boundary are
  the only guardrails. Recommend verifying the marker + apply path on one real
  finding before flipping INFRA_PREAMBLE.
- **Cross-repo:** symphony (marker + scheduler handling + UI + window helper +
  dedup guard); homelab (INFRA_PREAMBLE rule). Independent `main` commits.
- **Plane path unaffected** — Podium-scoped; Plane patrols keep blocking.
- Reuses the dormant `scheduled_for` / `Symphony-Schedule` machinery rather than
  reinventing it.

## Status

`proposed` — ADR written + wiki captured 2026-06-20. **Partially built 2026-06-21 by #93, #94, and #95:** schedule foundations landed (`next_maintenance_window`, `next_window`, Podium `prefer_last`), the stdout marker parser/output-contract mechanism landed, and scheduler terminal handling now converts valid infra markers into scheduled TODO issues while blocking malformed/past/reasonless markers. Still unbuilt: INFRA_PREAMBLE schedule-authorization policy, dedup-don't-clobber behavior, and the Podium UI Schedule control. Claims C-0289 (machinery exists, gate requires comment), C-0290 (cron never in window), C-0291 (ADR route), C-0292/C-0293 (#93 foundations), C-0294 (#94 marker mechanism), C-0295 (#95 terminal handling).

## Related

- [ADR-0015 — patrol→Podium tracker adapter](adr-0015-patrol-podium-tracker-adapter.md) — the per-state contract this extends
- [ADR-0016 — WORKFLOW.md retired → INFRA_PREAMBLE constant](adr-0016-workflow-md-retired-renderer-constant.md)
- [ADR-0005 — replace Plane with Podium](adr-0005-replace-plane-with-podium.md)
- [Schedule comment grammar](../concepts/schedule-comment-grammar.md)
- [Scheduler loop](../concepts/scheduler-loop.md)
- [Output contract (#046/#052)](podium-046-unified-output-contract.md) — where the `SYMPHONY_SCHEDULE` marker joins `SYMPHONY_RESULT`/`SYMPHONY_SUMMARY`/`SYMPHONY_QUESTION`
