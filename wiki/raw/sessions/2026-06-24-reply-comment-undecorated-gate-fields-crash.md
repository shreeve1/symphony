# Session — reply/comment crash: undecorated gate fields blow up the flyout

**Date:** 2026-06-24
**Symptom (operator):** "I was trying to send a message in an issue and got: *Application error:
a client-side exception has occurred (see the browser console for more information).*"

## Root cause (verified)

The crash was a **frontend render exception**, not an API error.

- The `#110` dependency-chip feature (ADR-0021) renders `unsatisfied_blocked_by` and
  `lock_conflicts` on a `todo` issue. In `web/frontend/components/IssueFlyout.tsx`,
  `GateHints` read `issue.unsatisfied_blocked_by.length` / `issue.lock_conflicts.join(...)`
  **unguarded** (the `IssueDetail` type marks them required).
- Those two fields are NOT base columns — they are added by `_decorate_issue_gates`
  (`web/api/main.py:692`), which only ran on `GET /api/bindings/{name}/issues`,
  `GET /api/issues/{id}`, the create path, and `patch_issue`.
- The mutation endpoints `/reply` and `/comment` returned **and websocket-published**
  a bare `_row(...)` payload that skipped `_decorate_issue_gates`, so the gate fields
  were absent.
- Crash chain: send reply → `/reply` flips state to `todo` and publishes the
  undecorated row → `QueryProvider.tsx` `issue.updated` handler does
  `setQueryData(["issue", id], row)` → the flyout re-renders → `GateHints` runs (it
  only renders for `todo`) → `undefined.length` → client-side exception.

## Fix (commit 76d5d0d, formatting follow-up 06fbe2b)

Defense in depth:

- **Backend (root cause):** `/reply` and `/comment` now return + publish
  `_decorate_issue_gates(connection, [_row(row)])[0]`, so their responses and
  websocket payloads carry `unsatisfied_blocked_by`, `lock_conflicts`,
  `dependencies_satisfied`.
- **Frontend (belt + suspenders):** `GateHints` defaults the fields to `[]`
  (`issue.unsatisfied_blocked_by ?? []`), matching the already-defensive `IssueCard`
  /`GateTags`, so any still-undecorated payload (steer/abort/schedule/dismiss and
  their bare `_row` returns at `web/api/main.py:1683/1740/1782/1807/1833/1865/1902`)
  can't crash the flyout.
- **Regression test:** `web/api/tests/test_reply.py::test_reply_response_carries_gate_fields`
  asserts the reply response includes the gate fields.

## Deploy

Backend fix lives in `podium-api` (uvicorn `main:app`), frontend in `podium-web`
(`next start`) — NOT `symphony-host` (the scheduler). Both were restarted: `podium-api`
via `sudo systemctl restart podium-api.service`; `podium-web` via the atomic
`web/frontend/deploy.sh` (build→stop→swap→start). `symphony-restart` is the wrong
skill here — it only controls the scheduler.

## Lesson / standing rule

Any endpoint that returns or publishes an issue row consumed by the board/flyout must
either run `_decorate_issue_gates` OR the frontend must default the decorated fields.
The bare `_row` returns on the remaining mutation endpoints (steer/abort/schedule/
dismiss/merge) are now only safe because of the frontend guard — decorate them too if
a component ever reads a decorated field as required.
