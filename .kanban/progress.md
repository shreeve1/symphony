# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

# Conventions & Decisions

- Inbox is the canonical sidebar membership list for operator-response issues; membership is a projection and does not move issues between board columns.
- Inbox membership uses `in_review` and `blocked` issues across non-archived bindings, ordered by `COALESCE(last_event_at, updated_at) DESC, id DESC`.
- Inbox dismissal is represented by nullable `issue.inbox_dismissed_at`; read-path filtering excludes rows dismissed at or after latest activity and allows newer activity to resurface cards.

# Iteration Log

## #037 Podium Inbox read path — 2026-06-12

**What changed:** Added `inbox_dismissed_at` migration/schema parity, authenticated `GET /api/inbox`, backend tests, Sidebar Inbox query/cards, live invalidation, fixtures, and Playwright inbox tests.
**Files:** `web/api/main.py`, `web/api/schema.py`, `web/api/migrations/versions/0005_inbox_dismissed_at.py`, `web/api/tests/test_inbox.py`, `web/frontend/lib/api.ts`, `web/frontend/components/Sidebar.tsx`, `web/frontend/components/QueryProvider.tsx`, `web/frontend/tests/fixtures.ts`, `web/frontend/tests/inbox.spec.ts`.
**Decisions:** Used TanStack Query invalidation for `issue.created` / `issue.updated` events instead of direct cache surgery; kept 10s polling fallback.
**Conventions established:** Inbox sections hide completely when empty; cards deep-link with `/{binding_name}?issue={id}`.
**Notes for next iteration:** #038 owns writing `inbox_dismissed_at`, dismiss button UX, and explicit resurface clearing on transitions into `in_review` or `blocked`.

## #038 Podium Inbox dismiss + resurface — 2026-06-12

**What changed:** Added `POST /api/issues/{id}/dismiss`, optimistic Sidebar dismiss controls, API/backend resurface coverage, tracker transition dismissal clearing, and Playwright coverage for hover-dismiss without navigation.
**Files:** `web/api/main.py`, `tracker_podium.py`, `web/api/tests/test_inbox.py`, `tests/test_tracker_podium.py`, `web/frontend/lib/api.ts`, `web/frontend/components/Sidebar.tsx`, `web/frontend/tests/inbox.spec.ts`, `web/frontend/tests/fixtures.ts`, `web/frontend/tests/live-sync.spec.ts`, `web/frontend/tests/new-issue.spec.ts`.
**Decisions:** Dismissal is state-preserving; transitions into `in_review`/`blocked` clear `inbox_dismissed_at`; newer `last_event_at` remains a secondary resurface path.
**Conventions established:** Inbox dismiss buttons use optimistic removal with rollback and do not navigate the card.
**Notes for next iteration:** #039 can remove the dashboard attention list now that Inbox read + dismiss flows are in place.
