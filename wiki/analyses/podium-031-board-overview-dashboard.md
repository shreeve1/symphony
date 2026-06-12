---
title: "Podium #031 — board overview dashboard"
type: analysis
status: promoted
created: 2026-06-12
updated: 2026-06-12
sources:
  - web/frontend/app/page.tsx
  - web/frontend/app/[binding]/page.tsx
  - web/frontend/components/KanbanBoard.tsx
  - web/frontend/tests/dashboard.spec.ts
  - .kanban/issues/031-podium-board-overview-dashboard.md
  - .kanban/progress.md
confidence: high
tags: [podium, web-ui, dashboard, ralph]
---

# Podium #031 — board overview dashboard

#031 landed the ADR-0006 board-overview slice: the root route `/` is now an at-a-glance dashboard rather than a placeholder. It uses existing binding and issue-list APIs, so no backend aggregate endpoint was added. [source: web/frontend/app/page.tsx] [source: .kanban/issues/031-podium-board-overview-dashboard.md]

## Dashboard contract

The dashboard fetches bindings, skips archived bindings, then fetches each active binding's existing issue-list payload. Per-binding cards and the global roll-up count issues by `issue.state` for the five board states (`todo`, `running`, `in_review`, `blocked`, `done`), so the dashboard and Kanban board use the same state source. [source: web/frontend/app/page.tsx]

Each binding card shows last activity by taking the max `last_event_at` value across that binding's issues and rendering an age string. This keeps quiet bindings visible without adding a server-side aggregate. [source: web/frontend/app/page.tsx]

## Attention list and deep links

The cross-binding attention list includes issues where `state === "blocked"`, `latest_verdict === "blocked"`, or `latest_run_state === "failed"`. Each row links to `/<binding>?issue=<id>`. [source: web/frontend/app/page.tsx]

Binding pages now read the `issue` query parameter and pass it to `KanbanBoard` as `initialIssueId`; `KanbanBoard` seeds the selected issue from that prop and clears the query parameter with `router.replace()` when the flyout closes. Normal card-click behavior is unchanged. [source: web/frontend/app/[binding]/page.tsx] [source: web/frontend/components/KanbanBoard.tsx]

## Verification

Playwright coverage seeds mixed states across bindings, asserts per-binding counts, global counts, attention membership, attention-row click-through into the issue flyout, and query cleanup on close. Full Ralph verification passed: `uv run pytest` (591 passed, 1 skipped), `pnpm exec tsc --noEmit`, `pnpm test:e2e` (21 passed), touched-file LSP diagnostics clean, and fresh review `RALPH_REVIEW: PASS`. [source: web/frontend/tests/dashboard.spec.ts] [source: .kanban/progress.md]

## Claims

C-0116 in [CLAIMS.md](../CLAIMS.md).
