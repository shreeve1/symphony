---
title: "ADR-0006 — Engine state surfaced by gated polling, not the WebSocket"
type: analysis
status: promoted
created: 2026-06-12
updated: 2026-06-12
sources:
  - wiki/raw/adr-0006-engine-state-polling.md
  - docs/adr/0006-engine-state-surfaced-by-polling-not-websocket.md
  - web/api/main.py
  - agent_runner.py
  - scheduler.py
confidence: high
tags: [podium, websocket, polling, observability, scheduler, architecture, adr, decision]
---

# ADR-0006 — Engine state surfaced by gated polling, not the WebSocket

## Context

ADR-0005 ships Podium as three independent processes — the Symphony scheduler (`symphony-host.service`), the FastAPI/uvicorn API (`podium-api.service`), and the Next.js frontend (`podium-web.service`). #017 added `WS /api/ws` with an in-process `WebSocketHub` to push live state. The latent gap: the hub is **in-process to the API only**, and the scheduler is a separate process that writes Run/Issue rows **directly to the shared SQLite store** via `tracker_podium` — it never touches the hub. [source: wiki/raw/adr-0006-engine-state-polling.md]

## Verified finding

The only `run.updated` publish in the codebase is the API-startup seed publish at `web/api/main.py:126`; `grep -c "run.updated" scheduler.py tracker_podium.py` returns `0` in both. So **engine-driven Run/Issue state changes are never pushed over the WebSocket** — the board and run detail only catch up on a manual refetch or TanStack tab-refocus. This was already flagged open in #017 (`analyses/podium-017-live-updates.md` — "Real engine-driven `run.updated` publishing remains a #020 integration task") and in C-0070; #020 did not wire it, and architecturally it cannot go through the in-process hub. [source: web/api/main.py] [source: scheduler.py]

The run log compounds it: `agent_runner.py:272` uses `process.communicate(timeout=…)`, which blocks until pi exits and captures all stdout/stderr at once. The log lands only at completion — there is no incremental output to tail even if the transport existed. [source: agent_runner.py]

## Decision

Surface engine-driven state changes with **gated frontend interval polling** (TanStack `refetchInterval`): fast (~3s) while any Issue is `queued`/`running`, slow/off when idle, against local WAL-mode SQLite. The WebSocket is retained for instant optimistic feedback on the operator's own UI actions (create/PATCH). Run liveness rides the same lever: a client-side elapsed timer from `started_at`, and metadata/duration/log refreshing through the poll when pi exits — no live log tail.

## Rejected alternatives

- **Scheduler→API notify** (scheduler POSTs a localhost API endpoint that fans out over the WS): true push, but couples the scheduler to the auth-gated API being up, needs an internal auth path through the #018 gate, and adds failure handling — coupling ADR-0005 deliberately avoided, for latency a single operator does not need.
- **API-side DB poller** (API polls SQLite for changed rows and publishes over WS): centralizes polling for many clients, but this is single-user; pure overhead here.
- **True live log streaming** (rewrite dispatch to stream pi stdout line-by-line + push over WS): touches the core dispatch path and the silent-exit guard (`agent_runner.py:281`); runs are already bounded by `run_timeout_ms` with orphans reaped by the #022 restart reconciler.

## Consequences

Pull-not-push with ~3s latency while active; each browser tab polls independently — both immaterial for a single-operator console. Reversible: a scheduler→API notify path can be added later against the same WebSocket, narrowing or dropping polling at that point.

## Status note

This ADR was authored during a `/grill-me` planning session for a Podium UX/observability tuning effort (searchable agent-filtered model dropdowns via `models.yml` + `symphony-models`/`symphony-skills` skills, run elapsed timer, board overview at `/`). Only the live-bridge decision is recorded as an ADR. The model-catalog/dropdown slice later landed in #028 and is tracked separately in `podium-028-model-catalog-searchable-dropdowns.md`; polling, run elapsed timer, board overview, and maintenance skills remain separate slices. [source: wiki/analyses/podium-028-model-catalog-searchable-dropdowns.md]

## Claims

C-0112, C-0113 in [CLAIMS.md](../CLAIMS.md). Closes the open question in C-0070. Related implementation claims: C-0114, C-0115.
