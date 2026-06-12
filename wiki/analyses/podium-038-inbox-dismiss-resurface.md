---
title: Podium #038 — Inbox dismissal and resurface
type: analysis
status: promoted
created: 2026-06-12
updated: 2026-06-12
sources:
  - .kanban/issues/038-podium-inbox-dismiss-resurface.md
  - .kanban/progress.md
  - web/api/main.py
  - tracker_podium.py
  - web/api/tests/test_inbox.py
  - tests/test_tracker_podium.py
  - web/frontend/components/Sidebar.tsx
  - web/frontend/lib/api.ts
  - web/frontend/tests/inbox.spec.ts
confidence: high
tags: [podium, inbox, dismiss, resurface, websocket, sidebar]
---

# Podium #038 — Inbox dismissal and resurface

#038 completed the write path for the Inbox projection that #037 introduced. Inbox dismissal is state-preserving: dismissing a card hides it from the Inbox without moving the Issue out of its board column [source: .kanban/issues/038-podium-inbox-dismiss-resurface.md]. `POST /api/issues/{issue_id}/dismiss` is auth-protected by the existing `/api/*` middleware, returns 404 for unknown Issues, and performs one guarded SQL write that sets `inbox_dismissed_at` and bumps `updated_at` only when the Issue is currently `in_review` or `blocked`; other states return 409. After the write it returns the updated Issue row and publishes `issue.updated` through the in-process WebSocket hub [source: web/api/main.py] [source: web/api/tests/test_inbox.py].

## Resurface rules

The Inbox read path still admits dismissed cards when newer activity exists because its filter compares `inbox_dismissed_at` against `COALESCE(last_event_at, updated_at)` [source: web/api/main.py]. #038 added the authoritative transition-based resurface path: any write that moves an Issue into `in_review` or `blocked` clears `inbox_dismissed_at`, so a previously dismissed Issue becomes visible even when the transition itself does not update `last_event_at` [source: .kanban/issues/038-podium-inbox-dismiss-resurface.md]. This is implemented in the operator PATCH path, `PodiumTrackerAdapter.transition_state()`, orphan-run reconciliation to `blocked`, and the API's worktree/merge blocked helper [source: web/api/main.py] [source: tracker_podium.py]. Tests cover PATCH and tracker transitions into Inbox states clearing dismissal, while transitions into other states preserve it [source: web/api/tests/test_inbox.py] [source: tests/test_tracker_podium.py].

## Frontend behavior

Sidebar Inbox cards now expose a small check-mark dismiss button on hover/focus. The button sits outside the card navigation link, calls `dismissIssue(id)`, removes the card optimistically from the `['inbox']` TanStack Query cache, restores the previous cache on error, and invalidates `['inbox']` when settled [source: web/frontend/components/Sidebar.tsx] [source: web/frontend/lib/api.ts]. Playwright coverage verifies the button appears on hover, clicking it does not navigate, the card leaves the Inbox, and the Issue remains visible in its board column [source: web/frontend/tests/inbox.spec.ts].

## Verification

Implementation verification for #038 used the repo-correct Python runner and frontend checks: `PATH=/home/james/.local/bin:$PATH uv run pytest -q` passed 652 tests with 1 skipped; `cd web/frontend && pnpm exec tsc --noEmit` passed; `cd web/frontend && PATH=/home/james/.local/bin:$PATH pnpm test:e2e` passed 37 tests [source: .kanban/issues/038-podium-inbox-dismiss-resurface.md]. Fresh Ralph review returned `RALPH_REVIEW: PASS_WITH_NOTES`; notes were unrelated test-maintenance drift, with all #038 acceptance criteria satisfied [source: .kanban/issues/038-podium-inbox-dismiss-resurface.md].

## Follow-up

#039 can remove the dashboard attention list because Inbox read and dismiss flows are now both in place [source: .kanban/progress.md].

## Claims

C-0137..C-0139 in [CLAIMS.md](../CLAIMS.md).
