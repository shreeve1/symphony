---
id: 057
title: Podium flyout steer box + tail panel (pi live Steering UI) — Slice D
status: done
blocked_by: [053, 056]
parent: null
priority: 0
created: 2026-06-13
updated: 2026-06-14
actor: ralph
---

## What to build

The operator-facing surface for live Steering: extend the #053 tail flyout with a steer input so the operator can watch a running pi Run and redirect it mid-task. Frontend + thin wiring only; the channel and tail are #056/#053.

- A steer input box in the issue flyout, enabled only when the open issue has a live RPC pi run (disabled/hidden otherwise, including for Claude runs — show "park-and-reply only" affordance there).
- Submitting posts to the #056 steer endpoint; show the in-flight steer in the tail stream (queued → delivered) using the RPC `queue_update`/tail signal so the operator sees it land. The steer is also written to `comments_md` by #056 as an `### Operator Steer` entry — the durable record — so it shows in the comments thread (the tail view is transient); no extra write here, just ensure the comments tab reflects it.
- An abort/stop control wired to the #056 abort path.
- Reuse the #053 tail panel for the live view; rebind on issue switch; degrade gracefully when no run is active.

## Acceptance criteria

- [x] Steer box appears and is enabled only for an issue with a live pi RPC run; absent/disabled for Claude and idle issues.
- [x] Submitting a steer posts to the #056 endpoint and the operator sees it reflected in the live tail (queued/delivered).
- [x] Abort control stops the run and the flyout reflects completion.
- [x] Switching issues rebinds tail + steer to the newly-open issue; no cross-issue leakage.
- [x] e2e covers: open a (faked) live run, stream tail, submit a steer, see it appear.

## Verification

`uv run pytest web/api/tests/ -q` for endpoint wiring AND `cd web/frontend && npm run test:e2e -- steer-flyout.spec.ts`.

## Blocked by

- Blocked by #053, #056

## Implementation Notes

Added a live steering composer to the Session tab that enables only for active pi RPC runs, posts steer/abort requests to the existing `/api/issues/{id}/steer` endpoint, appends local queued/delivered tail entries, and refreshes issue comments so the durable `Operator Steer` / `Operator Abort` blocks appear. Exposed binding `pi_mode` through `/api/bindings`, added typed frontend steer/abort clients, and covered live steer, disabled Claude/idle states, abort, and tail/comment visibility with `steer-flyout.spec.ts`.
