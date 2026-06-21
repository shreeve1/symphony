---
id: 95
title: Scheduler terminal handler — agent SYMPHONY_SCHEDULE → held + TODO
status: pending
blocked_by: [93, 94]
parent: null
priority: 0
created: 2026-06-21
---

## What to build

Wire the `SYMPHONY_SCHEDULE` marker into `_classify_terminal`
(`scheduler/__init__.py:1615`) so a clean infra agent run that emits the marker
defers the issue into the maintenance window instead of completing/blocking. This
completes the hands-off agent tracer bullet end-to-end: the existing engine
(`_select_scheduled_candidate`/`_release_scheduled_candidate`/`_with_schedule_context`,
`scheduled-held` gate at `:1267`) then releases and re-dispatches it in-window.

Behavior:

1. After `verdict = _parse_result_marker(class_stdout)` (`:1719`) and the
   permission-gate check, parse the schedule marker from the raw `class_stdout`.
   **Precedence:** hard failures (timeout/nonzero/permission-gate) win; then the
   **schedule** marker; then question; then `blocked`; then review/done. A schedule
   marker takes precedence over a stray `SYMPHONY_RESULT`/approval-gate so a
   deferred run is never misclassified as blocked.
2. On a valid schedule marker, infra only (`not is_coding`): post
   `format_schedule_comment(not_before=..., reason=...)` via `adapter.add_comment`;
   `adapter.add_labels(candidate.id, [TrackerRole.SCHEDULED])` (sets
   `scheduled_for=now` → held); `adapter.transition_state(candidate.id,
   TrackerRole.STATE_TODO)`. Order: comment first, then label, then TODO (so a held
   issue always has a valid `Symphony-Schedule:` comment for
   `_select_scheduled_candidate`).
3. Finish the run record `state="succeeded"`, `verdict=None` (the run `verdict`
   CHECK allows NULL; the issue stays in TODO, not a CHECK-constrained state — no
   new issue state, avoiding the C-0211 trap), `summary=<agent summary>`.
4. Return `TickResult(True, "agent-marker-scheduled", candidate.id, mode=mode)` and
   emit a `state_scheduled` log line (issue_id, not_before).
5. Malformed marker (`not_before` unparseable / explicit past / empty reason):
   block the issue with a clear reason (mirror `_detect_agent_schedule`'s
   `agent-scheduled-malformed` at `:2807`); never silently drop.
6. Coding bindings ignore the marker (no scheduling).

## Acceptance criteria

- [ ] A clean infra run emitting a valid `SYMPHONY_SCHEDULE` marker calls `add_comment(format_schedule_comment(...))`, then `add_labels([SCHEDULED])`, then `transition_state(TODO)`, in that order.
- [ ] The run record is finished `succeeded` with `verdict=None`; the issue ends in TODO.
- [ ] Returns reason code `agent-marker-scheduled`; the marker takes precedence over a co-emitted `SYMPHONY_RESULT: blocked` and over an approval-gate false positive.
- [ ] A malformed/past/reasonless marker blocks the issue with an explanatory comment (no silent drop).
- [ ] A coding binding ignores the marker (no comment/label/transition).
- [ ] A marker-scheduled issue is held by `_gate_run_tick_candidate` (`scheduled-held`) before `not_before` and released by `_select_scheduled_candidate` once `now >= not_before` (use a controllable `now`).

## Verification

`uv run pytest tests/test_scheduler.py -q`

## Blocked by

- Blocked by #93 (next_window helper) and #94 (`_parse_schedule_marker`).
