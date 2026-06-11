---
title: Podium #017 — WebSocket live updates
type: analysis
status: promoted
created: 2026-06-11
updated: 2026-06-11
sources:
  - web/api/main.py
  - web/api/seed.py
  - web/api/tests/test_websocket.py
  - web/frontend/components/QueryProvider.tsx
  - web/frontend/components/NewIssueModal.tsx
  - web/frontend/tests/live-sync.spec.ts
  - web/frontend/playwright.config.ts
confidence: high
tags: [podium, websocket, live-updates, tanstack-query, fastapi, playwright]
---

# Podium #017 — WebSocket live updates

Slice #017 replaced board freshness-by-polling with a single browser-session WebSocket plus server-side in-process fanout. The implementation landed in commit `0a50bc7` and depends on `websockets` because uvicorn requires a WebSocket protocol implementation for browser e2e. [source: web/api/main.py] [source: pyproject.toml]

## Backend contract

`WS /api/ws` accepts subscribers and streams JSON messages from an in-process `WebSocketHub`. The hub keeps one bounded `asyncio.Queue` per connected socket, drops stale subscribers whose queue fills, logs connect/disconnect, and has no room/topic filtering yet. This is intentionally single-worker only; no Redis or cross-process broker exists. [source: web/api/main.py]

Issue writes publish after successful DB commits:

- `PATCH /api/issues/{issue_id}` publishes `{"type":"issue.updated","id":issue_id,"row":row}` after changed fields commit. No-op patches still return the current row and do not publish. [source: web/api/main.py]
- `POST /api/bindings/{name}/issues` publishes `{"type":"issue.created","binding_name":name,"row":row}` after insert commit. [source: web/api/main.py]
- Startup seeding now returns inserted run IDs; lifespan reads those rows and publishes placeholder `run.updated` events for seeded runs. Real engine-driven `run.updated` publishing remains a #020 integration task. [source: web/api/seed.py] [source: web/api/main.py]

## Frontend contract

`QueryProvider` opens one WebSocket per browser session. On open it marks the session connected and invalidates visible binding/issue queries to recover missed events. On close it marks disconnected and retries with delays `1s, 2s, 5s, 10s, 10s...`; browser offline/online events also drive the disconnect pill state and reconnect/refetch path. [source: web/frontend/components/QueryProvider.tsx]

Message handlers update TanStack Query caches directly:

- `issue.created` upserts the row into the binding issue list and stores detail under `['issue', id]`.
- `issue.updated` updates issue detail and every `['issues', ...]` list cache.
- `run.updated` updates `['run', id]` and every `['runs', ...]` list cache. [source: web/frontend/components/QueryProvider.tsx]

The header shows `Disconnected — retrying` only while the WebSocket is not connected. The Next Playwright server exports `NEXT_PUBLIC_PODIUM_API_ORIGIN` so browser WebSocket tests connect directly to the e2e FastAPI origin instead of relying on Next rewrite WebSocket proxying. [source: web/frontend/app/layout.tsx] [source: web/frontend/playwright.config.ts]

## Optimistic-create race fix

Live `issue.created` events can race with the existing #014 optimistic create flow. The modal success handler now deduplicates by canonical `id`, and the live-upsert path replaces a matching negative temp card (`same binding_name + title`) rather than adding a second card. [source: web/frontend/components/NewIssueModal.tsx] [source: web/frontend/components/QueryProvider.tsx]

## Concurrency decision

The #013 carry-over asked whether live tabs require optimistic concurrency. #017 keeps last-write-wins semantics: no version column, ETag, or conditional PATCH was added. WebSocket sync makes concurrent edits visible faster but does not prevent stale clobbering. [source: web/api/main.py]

## Verification

Backend coverage: `web/api/tests/test_websocket.py` checks two-client `issue.updated` delivery, instrumented publish call counts for PATCH/POST, reconnect delivery, and an integration-gated `test_workers_assumption` for uvicorn `--workers 1`. [source: web/api/tests/test_websocket.py]

Frontend coverage: `web/frontend/tests/live-sync.spec.ts` opens two browser contexts and asserts a state edit in one context appears in the other within 3s without reload; it also checks the disconnected pill during offline/online reconnect. [source: web/frontend/tests/live-sync.spec.ts]

Verification run for #017: `uv run pytest` passed 495 tests with 1 integration skip; `pnpm test:e2e` passed 13 Playwright tests; `pnpm exec tsc --noEmit` passed. `pnpm lint` still prompts for ESLint setup because no ESLint config is committed, so lint is a project tooling gap, not a #017 implementation failure.

## Claims

C-0069..C-0072 in [CLAIMS.md](../CLAIMS.md).
