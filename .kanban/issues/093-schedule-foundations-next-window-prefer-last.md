---
id: 93
title: Schedule foundations — next_maintenance_window helper + Podium prefer_last latest-control-line
status: done
blocked_by: []
parent: null
priority: 0
created: 2026-06-21
updated: 2026-06-21
actor: ralph
action_reviewed: 2026-06-21
---

## What to build

Shared backend foundations for ADR-0018 window scheduling, reusing the existing
scheduling engine. Two pieces, both pure backend logic:

1. **`next_maintenance_window(now)` helper.** Promote the window computation
   currently inlined in `scheduler/__init__.py:_default_scheduled_label_event`
   into a reusable helper that returns BOTH the window start (next/current 00:00
   `America/Los_Angeles`) and the advisory end (06:00) — return a
   `tuple[datetime, datetime]` or a `ScheduleEvent`; do NOT reduce to a bare
   `datetime` (that would lose the advisory `not_after`/late marking). Keep
   `_default_scheduled_label_event` working as a thin wrapper over it.
   `SCHEDULED_LABEL_WINDOW_TZ/START_HOUR/END_HOUR` stay the single source. Place
   the helper where both `scheduler/` and `web/api/main.py` can import it
   (`schedule.py` or a small `maintenance_window.py`). Support resolving the
   symbolic string `next_window` to the start via this helper. A `next_window`
   resolved while already inside the window (e.g. 01:00 LA → today's 00:00) is
   valid and must NOT be treated as a past time.

2. **Podium `prefer_last` latest-control-line selection.** `parse_schedule_comment`
   (`schedule.py:522`) currently `break`s on the FIRST `Symphony-Schedule:` /
   `Symphony-Schedule-Cancelled:` line. Podium `tracker_podium.list_comments`
   projects all of `comments_md` as ONE synthetic comment, so appending a
   reschedule or cancellation leaves the OLD schedule winning. Add a
   `prefer_last: bool` parameter that keeps the LAST matching control line, and
   **thread it through the real call path**: `scheduler/__init__.py:_latest_schedule_event`
   → `schedule.py:latest_event` → `parse_schedule_comment`. Set it `True` for the
   Podium single-blob path (a Podium branch in `_latest_schedule_event` or a
   `CandidateComment` flag). Plane stays first-match (default `prefer_last=False`)
   for back-compat.

## Acceptance criteria

- [x] `next_maintenance_window(now)` exists in a module importable by both `scheduler` and `web/api/main.py`, returns window start AND advisory end, and `_default_scheduled_label_event` delegates to it with unchanged behavior.
- [x] The symbolic value `next_window` resolves to the next/current window start via the helper; resolving inside the window yields a start that is not flagged as past.
- [x] `parse_schedule_comment(..., prefer_last=True)` returns the LAST control line in a multi-control-line body; `prefer_last=False` (default) preserves the existing first-match behavior.
- [x] `latest_event(..., prefer_last=...)` exists and `_latest_schedule_event` passes `prefer_last=True` for Podium single-blob comments.
- [x] On a Podium `comments_md` blob with schedule→cancel: cancellation wins. With schedule→reschedule: the latest `not_before` wins. With schedule→cancel→reschedule: the reschedule wins.
- [x] All existing `tests/test_schedule.py` and `tests/test_scheduler.py` cases still pass (no Plane regression).

## Verification

`uv run pytest tests/test_schedule.py tests/test_scheduler.py -q`

## Blocked by

None — can start immediately.

## Implementation Notes

- Added `schedule.next_maintenance_window(now)` with shared window constants and made the scheduler's label-only default schedule path delegate to it.
- Added `not_before=next_window` resolution through the schedule parser.
- Added `prefer_last` threading from `_latest_schedule_event` → `latest_event` → `parse_schedule_comment`, enabled for Podium single-blob comments while preserving Plane/default first-match behavior.
- Verified with `uv run pytest tests/test_schedule.py tests/test_scheduler.py -q` and LSP diagnostics on touched files.
