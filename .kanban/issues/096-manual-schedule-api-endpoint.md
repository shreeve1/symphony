---
id: 96
title: Manual schedule API — POST/DELETE /api/issues/{id}/schedule + binding_type + atomic create
status: done
blocked_by: [93]
parent: null
priority: 0
created: 2026-06-21
updated: 2026-06-21
action_reviewed: 2026-06-21
actor: ralph
---

## What to build

The backend for operator-driven scheduling (infra bindings only), on the same
label+comment rails the agent handler uses. Backend-only; UI is issue 97.

1. **`POST /api/issues/{id}/schedule`** (`web/api/main.py`) accepting
   `{not_before: "next_window" | iso8601-with-offset, reason?: str}`:
   - Resolve `next_window` server-side via the issue-93 `next_maintenance_window`
     helper. Default `reason` to `"operator scheduled via Podium"` when omitted
     (`schedule.py` requires a non-empty reason).
   - Atomically: append the `format_schedule_comment` body to `comments_md`; set
     `scheduled_for=now` (→ derived SCHEDULED label → held); **set `state='todo'`**
     (CRITICAL — `_select_scheduled_candidate` only scans `STATE_TODO`); bump
     `updated_at`; publish `issue.updated`; wake the scheduler (reuse the
     wake-sentinel path used by `/reply`).
   - Reject non-infra bindings (use `_binding_type_for`) with 400; reject an issue
     with an active run (reuse `ACTIVE_RUN_STATES = ("queued","running")`) with 409;
     reject `archived`; reject an explicit past `not_before` with 422 (a
     `next_window` resolving inside the window is NOT past).
   - Do NOT set a future `scheduled_for` value (a future value derives no SCHEDULED
     label → not held → dispatched immediately).
2. **`DELETE /api/issues/{id}/schedule`** accepting `{reason?: str}` (default
   `"operator unscheduled via Podium"`): clear `scheduled_for` (removes the derived
   label) and append a `Symphony-Schedule-Cancelled:` comment
   (`format_cancellation_comment`). Relies on issue-93 `prefer_last` so the
   appended cancellation is the control line the parser selects on the Podium blob.
3. **Expose `binding_type` on `/api/bindings`** rows (`list_bindings`, `:649`) so
   the new-issue modal can gate the control (issue 97). Do not infer type from name.
4. **Atomic create-and-schedule**: extend `IssueCreate` with an optional
   `schedule: {not_before, reason}` that writes the row + canonical schedule comment
   + `scheduled_for=now` + `state='todo'` in one transaction — closes the
   create-then-schedule dispatch race (a plain create inserts `state='todo'` and
   could be dispatched before a follow-up call adds the hold).

## Acceptance criteria

- [x] `POST /schedule` with `{not_before:"next_window"}` sets `scheduled_for=now` + `state='todo'` + a `Symphony-Schedule:` comment; the issue is held next tick.
- [x] `POST /schedule` defaults a missing `reason`; non-infra binding → 400; queued OR running active run → 409; explicit past `not_before` → 422; `next_window` resolving inside the window is accepted.
- [x] `DELETE /schedule` clears the schedule and appends a `Symphony-Schedule-Cancelled:` comment; the issue becomes dispatchable again (parser selects the cancellation via prefer_last).
- [x] `/api/bindings` rows include `binding_type`.
- [x] Atomic create-and-schedule writes row + comment + `scheduled_for=now` + `state='todo'` together; the new issue is held with no dispatch-race window.

## Verification

`uv run pytest web/api/tests/test_schedule_endpoint.py web/api/tests/test_endpoints.py -q`

## Implementation Notes

Added infra-only `POST`/`DELETE /api/issues/{id}/schedule` endpoints, exposed `binding_type` on `/api/bindings`, and added atomic create-and-schedule support via `IssueCreate.schedule`. Backfilled API regression tests for scheduling, unscheduling, active-run/past/non-infra rejects, binding type, and create-time scheduling.

## Blocked by

- Blocked by #93 (`next_maintenance_window` / `next_window` resolution + `prefer_last`).
