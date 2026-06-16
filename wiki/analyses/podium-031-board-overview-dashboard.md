---
title: "Podium #031 — board overview dashboard"
type: analysis
status: promoted
created: 2026-06-12
updated: 2026-06-16
sources:
  - web/frontend/app/page.tsx
  - web/frontend/app/[binding]/page.tsx
  - web/frontend/components/KanbanBoard.tsx
  - web/frontend/tests/dashboard.spec.ts
  - .kanban/issues/031-podium-board-overview-dashboard.md
  - .kanban/issues/039-podium-remove-dashboard-attention-list.md
  - .kanban/progress.md
confidence: high
tags: [podium, web-ui, dashboard, ralph]
---

# Podium #031 — board overview dashboard

#031 landed the ADR-0006 board-overview slice: the root route `/` is now an at-a-glance dashboard rather than a placeholder. It uses existing binding and issue-list APIs, so no backend aggregate endpoint was added. [source: web/frontend/app/page.tsx] [source: .kanban/issues/031-podium-board-overview-dashboard.md]

## Dashboard contract

The dashboard fetches bindings, skips archived bindings, then fetches each active binding's existing issue-list payload. Per-binding cards and the global roll-up count issues by `issue.state`, but the dashboard total and state badges now include only active states (`todo`, `running`, `in_review`, `blocked`); terminal states (`done`, `archived`) are omitted from dashboard totals and badges while remaining available on the Kanban board. [source: web/frontend/app/page.tsx]

Each binding card shows last activity by taking the max `last_event_at` value across that binding's issues and rendering an age string. This keeps quiet bindings visible without adding a server-side aggregate. [source: web/frontend/app/page.tsx]

## Deep links and removed attention list

The original #031 cross-binding attention list has been removed by #039. The Dashboard now keeps only the global roll-up and per-binding cards; the Sidebar Inbox is the canonical operator-response surface, so `web/frontend/app/page.tsx` no longer contains `dashboard-attention`, `attention-row`, or `attentionItems`. [source: web/frontend/app/page.tsx] [source: .kanban/issues/039-podium-remove-dashboard-attention-list.md]

Binding pages still read the `issue` query parameter and pass it to `KanbanBoard` as `initialIssueId`; `KanbanBoard` seeds the selected issue from that prop and clears the query parameter with `router.replace()` when the flyout closes. Normal card-click behavior is unchanged. [source: web/frontend/app/[binding]/page.tsx] [source: web/frontend/components/KanbanBoard.tsx]

## Verification

Playwright coverage now asserts per-binding cards, global counts excluding `done`/`archived`, terminal state badge omission, and absence of the removed attention testids. #039 verification passed: `PATH=/home/james/.local/bin:$PATH pnpm test:e2e` (37 passed), `pnpm exec tsc --noEmit`, touched-file LSP diagnostics clean, and fresh review `RALPH_REVIEW: PASS`; the #38 update passed LSP diagnostics, `pnpm exec tsc --noEmit`, and targeted `PATH=/home/james/.local/bin:$PATH pnpm exec playwright test dashboard.spec.ts`. [source: web/frontend/tests/dashboard.spec.ts] [source: .kanban/progress.md]

## Claims

C-0116, C-0140, and C-0222 in [CLAIMS.md](../CLAIMS.md).
