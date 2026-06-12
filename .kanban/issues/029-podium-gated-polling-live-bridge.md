---
id: 029
title: Podium — gated interval polling for engine-driven state freshness
status: review
blocked_by: []
parent: null
priority: 0
created: 2026-06-12
updated: 2026-06-12
actor: ralph
---

## What to build

Make engine-driven Run/Issue state changes visible in the browser. Today
the WebSocket (#017) only carries mutations made *inside the API process*
(operator PATCH/create + the startup seed publish at `web/api/main.py:126`).
The scheduler is a **separate process** (`symphony-host.service`) that writes
Run/Issue rows directly to SQLite via `tracker_podium` and never reaches the
in-process `WebSocketHub` — so `todo→running→in_review`, run finalization,
and orphan reaping never push. `grep -c "run.updated" scheduler.py
tracker_podium.py` returns 0/0.

Decision: ADR-0006 — surface engine state via **gated frontend interval
polling**, keep the WebSocket for optimistic operator-action UI. Reversible
later via a scheduler→API notify path. See
`docs/adr/0006-engine-state-surfaced-by-polling-not-websocket.md` and
`wiki/analyses/adr-0006-engine-state-polling.md` (C-0112).

**1. Gated board polling.**

In the issue-list query (the `useQuery` for `["issues", binding]` in
`web/frontend/app/[binding]/page.tsx:13-17` — that is the real board query,
not just the mutation cache key), set `refetchInterval` to a function:
return `3000` when any issue in the binding is active, else `10000` (or
`false`). "Active" = `issue.state === 'running'` (the board's own running
column keys off `issue.state`, see `KanbanBoard.tsx:23`) **or**
`latest_run_state ∈ {queued, running}` (covers the brief window before the
issue flips to `running`). Keep `refetchOnWindowFocus`.

**2. Gated run-detail polling.**

In `RunDetailPanel` (`web/frontend/components/RunDetailPanel.tsx`), set
`refetchInterval` on the `["run", runId]` and `["run-log", runId]` queries
to `3000` while the run state is non-terminal (`queued`/`running`), and stop
(`false`) once terminal (`succeeded`/`failed`). This is what makes the log +
duration appear when pi exits.

**3. Leave the WebSocket as-is.**

Do not remove WS handling; it still drives instant optimistic UI for
operator create/PATCH. Polling and WS coexist (a poll that arrives first
just makes the WS event a no-op).

## Acceptance criteria

- [ ] Board issue-list query polls at ~3s while any issue is queued/running, and backs off to ~10s / off when idle (verify the `refetchInterval` function logic in a component/unit test).
- [ ] Run-detail run + log queries poll at ~3s while the run is non-terminal and stop once terminal.
- [ ] Playwright proves polling **in isolation from the WebSocket** (a direct API write would fan out over WS and mask polling): either mutate the row via a path that does not publish (direct SQLite write, as the scheduler does) or assert the update arrives with the WS disconnected. Board reflects the new state within ~4s **without a manual reload**.
- [ ] WebSocket optimistic-create / PATCH behavior from #017 still passes (`live-sync.spec.ts` unchanged and green).
- [ ] `pnpm exec tsc --noEmit` passes.

## Verification

```
cd /home/james/symphony && uv run pytest && \
cd web/frontend && pnpm exec tsc --noEmit && pnpm test:e2e
```

## Blocked by

- none
