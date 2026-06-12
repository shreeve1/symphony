---
id: 012b
title: Podium frontend shell — Next.js + Tailwind + shadcn + sidebar
status: done
blocked_by: [012a]
parent: null
priority: 0
created: 2026-06-10
---

## What to build

Frontend shell that talks to the #012a API. Renders a working sidebar
listing both bindings and a landing pane. No board, no flyout yet (those
land in #012c).

Stack:
- Next.js App Router at `web/frontend/`, port `8091`, binds `127.0.0.1`.
- Tailwind + shadcn/ui for components.
- TanStack Query for fetches (one query per endpoint, 5s `staleTime`).
- `pnpm` as the package manager.

Pages:
- `/` — root layout with sidebar on the left, landing pane on the right
  saying "Pick a binding from the sidebar". Sidebar reads
  `/api/bindings`, renders each as a clickable row.
- `/{binding}` — placeholder page showing the binding name and a "Board
  coming in #012c" message. Reads `/api/bindings/{name}/issues` purely to
  prove the fetch works; renders the count.

Layout:
- Sidebar fixed width (~240px), full height, dark background.
- Right pane fluid.
- Header strip with "Podium" title and a `(disconnected)` placeholder
  pill (real connection state lands in #017).

Files:
- `web/frontend/package.json` — Next.js 15, React 19, Tailwind, shadcn,
  TanStack Query, Playwright (dev).
- `web/frontend/app/layout.tsx`, `app/page.tsx`, `app/[binding]/page.tsx`.
- `web/frontend/components/Sidebar.tsx`.
- `web/frontend/playwright.config.ts` — `webServer` blocks start uvicorn
  on 8090 and `next dev` on 8091 for CI.
- `web/frontend/tests/sidebar.spec.ts` — visits `/`, asserts both
  bindings render, clicks one, asserts URL changes to `/{binding}`.

Out of scope: board columns, issue cards, flyout, editing — all in #012c.

## Acceptance criteria

- [x] `cd web/frontend && pnpm install && pnpm dev --port 8091` starts cleanly.
- [~] Port binds `127.0.0.1` only — **deviation:** default `HOST` changed to `0.0.0.0` for LAN access at operator request (`web/frontend/package.json` `dev`/`start`). Override with `HOST=127.0.0.1 pnpm dev`. Backend stays loopback; the Next rewrite proxy reaches it server-side. See Deviations below.
- [x] Visiting `http://localhost:8091/` renders sidebar with both `homelab` and `trading`.
- [x] Clicking a binding navigates to `/{binding}` and renders the issue count from the API.
- [x] Playwright `sidebar.spec.ts` passes via `pnpm test:e2e`.
- [x] `web/README.md` updated with `pnpm dev` / `pnpm test:e2e` commands.

## Verification

```
cd /home/james/symphony && uv run pytest && \
cd web/frontend && pnpm install && pnpm test:e2e
```

## Blocked by

- #012a (backend must serve `/api/bindings` and `/api/bindings/{name}/issues`)

## Deviations & notes (completion)

- **LAN bind:** `dev`/`start` default `HOST` is `0.0.0.0`, not `127.0.0.1` as the
  original criterion required. Operator chose LAN exposure; reachable at
  `http://10.20.20.16:8091/`. Unauthenticated — acceptable on trusted LAN only;
  auth lands in #018. Revert per-run with `HOST=127.0.0.1`.
- **Proxy, not CORS:** frontend reaches the backend via a Next rewrite
  (`/api/*` → `127.0.0.1:8090`, `next.config.mjs`), so all fetches are
  same-origin relative paths and the backend stays loopback-only.
- **Out-of-scope backend fix (#012a):** the console-error e2e test surfaced a real
  concurrency bug — FastAPI ran the sync DB dependency and endpoint on different
  threadpool threads, so SQLite raised `ProgrammingError` (cross-thread) and
  `/api/bindings` 500'd under concurrent fetches. Fixed with
  `check_same_thread=False` (`web/api/db.py`) plus a threaded regression test
  (`web/api/tests/test_endpoints.py::test_concurrent_reads_do_not_cross_threads`,
  proven fail-without-fix / pass-with-fix).
- **Extra tests beyond spec:** added `tests/fixtures.ts` (console / pageerror /
  requestfailed / httperror collector) and `tests/console.spec.ts`; wired
  `sidebar.spec.ts` into the same console gate.
- **Verified:** `uv run pytest` → 420 passed; `pnpm test:e2e` → 3 passed;
  `pnpm build` clean.
