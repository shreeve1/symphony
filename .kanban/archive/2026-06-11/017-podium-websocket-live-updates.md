---
id: 017
title: Podium WebSocket — live Issue + Run state updates
status: done
blocked_by: [013, 016]
parent: null
priority: 0
created: 2026-06-10
updated: 2026-06-11
actor: ralph
---

## What to build

Replace HTTP polling with WebSocket-driven live updates. Two open browser
tabs editing the same binding stay in sync without manual refresh.

Backend:

- `WS /api/ws` — single websocket endpoint. Client subscribes to all events
  for now (room/topic filtering deferred).
- Server emits messages on Issue and Run row mutations:
  - `{"type": "issue.updated", "id": …, "row": {...}}` after PATCH / POST.
  - `{"type": "issue.created", "binding_name": …, "row": {...}}` after POST.
  - `{"type": "run.updated", "id": …, "row": {...}}` (placeholder until
    engine integration in S020 actually mutates Run rows — for this slice,
    emit when seed creates a Run).
- Server uses a simple in-process pub/sub (no Redis, no broker — single
  uvicorn worker). The unit file (#023a) MUST pass `--workers 1` to
  uvicorn to preserve this assumption; assertion duplicated below.
- On disconnect, server logs and cleans up; no reconnect retry server-side.

Frontend:

- TanStack Query cache invalidations driven by WS messages.
- Reconnect strategy: exponential backoff (1s, 2s, 5s, 10s, cap 10s).
- On reconnect, refetch all visible queries (binding list + current binding's
  issues) to recover any messages missed during downtime.
- A subtle "Disconnected — retrying" pill renders in the header while the
  socket is down.

## Carry-over from #013 review

The PATCH endpoint (#013) has no optimistic-concurrency control: no
etag/version/if-match, so concurrent edits are last-write-wins and a stale
optimistic cache can clobber a newer server value. Acceptable single-operator,
but once two live tabs sync via WebSocket this becomes reachable — decide here
whether to add a version column / conditional PATCH or document last-write-wins
as the intended semantics. Related: `updated_at` monotonicity is only
guaranteed for sequential requests (per-request SQLite connections can race).

## Acceptance criteria

- [x] `web/api/tests/test_websocket.py` connects two clients, has client A PATCH an issue, asserts client B receives `issue.updated` within 1s.
- [x] PATCH endpoint (S013) emits at least one `issue.updated` event per successful mutation, observed within 1s on a subscribed client (test asserts via call-count instrumentation, not real-world behaviour).
- [x] POST endpoint (S014) emits at least one `issue.created` event per successful create, observed within 1s.
- [x] Disconnect → reconnect cycle test: client receives messages again after backoff.
- [x] Playwright `live-sync.spec.ts` opens two browser contexts, edits in one, asserts the other reflects the change within 3s with no manual reload.
- [x] Disconnect pill renders when WS server is killed; disappears on reconnect.
- [x] `web/api/tests/test_websocket.py::test_workers_assumption` asserts the running uvicorn process count is 1 (skipped in unit tests, runs in integration mode against the live unit).

## Verification

```
cd /home/james/symphony && uv run pytest && \
cd web/frontend && pnpm test:e2e
```

## Blocked by

- #013 (PATCH endpoint must exist to trigger `issue.updated`)
- #016 (Run detail view exercises `run.updated` events; note: the real `run.updated` assertion is moved into #020 where actual Run state mutations happen — this slice only proves the placeholder fires on seed)

## Implementation Notes

- Added `WS /api/ws` with a single-process in-memory WebSocket fanout hub.
- PATCH and POST issue mutations publish `issue.updated` and `issue.created` events after successful writes.
- Startup seeding returns run IDs and publishes placeholder `run.updated` events for seeded runs.
- Frontend opens one WebSocket connection per browser session, updates TanStack Query caches from messages, refetches visible queries on reconnect, and renders `Disconnected — retrying` while offline.
- Kept last-write-wins issue editing semantics for this slice; no version column or conditional PATCH was added.
