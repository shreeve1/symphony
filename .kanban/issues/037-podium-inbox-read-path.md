---
id: 037
title: Podium Inbox — read path: schema column, GET /api/inbox, sidebar section
status: review
blocked_by: []
parent: null
priority: 0
created: 2026-06-12
---

## What to build

The Inbox is a sidebar list of issues currently awaiting an operator response — one card per waiting issue, across all bindings, newest activity first. It is a projection: a card appearing in the Inbox never moves the issue; the issue stays in its board column. This slice ships the full read path end-to-end: the dismissal column (written by #038), the cross-binding API endpoint, and the sidebar UI with live updates.

Canonical terminology lives in `CONTEXT.md` under **Inbox** (it is an inbox — a membership list — not a feed or notifications).

**Schema.** New Alembic revision `0005_inbox_dismissed_at` adding `inbox_dismissed_at TIMESTAMP NULL` to the `issue` table (plain `ALTER TABLE ... ADD COLUMN`; no CHECK change, so no table rebuild needed — contrast `0004_archived_state`). Provide working `upgrade()` and `downgrade()`. Mirror the column in `SCHEMA_SQL` (`web/api/schema.py`) and bump `INITIAL_REVISION` to `0005_inbox_dismissed_at` so `tests/test_alembic_baseline.py` parity holds. Nothing writes the column in this slice; it exists so the inbox query's dismissal filter is real from day one.

**API.** New endpoint `GET /api/inbox` in `web/api/main.py` (session-auth like the other endpoints). Returns issues across all non-archived bindings where:

- `state IN ('in_review', 'blocked')`, and
- NOT dismissed: a row is excluded when `inbox_dismissed_at IS NOT NULL AND inbox_dismissed_at >= COALESCE(last_event_at, updated_at)`. (All-NULL column today makes this a no-op; #038 starts writing it. A later `last_event_at` than the dismissal resurfaces the card automatically.)

Ordered by `COALESCE(last_event_at, updated_at) DESC, id DESC`. Response rows use the same shape as the binding issue-list endpoint (omit `comments_md` / `context_md`) and must include `binding_name`, `state`, `last_event_at`, and `inbox_dismissed_at`.

**Frontend.** New "Inbox" section in `web/frontend/components/Sidebar.tsx`, placed **below** the existing Bindings section, inside the scrollable nav. Behavior:

- Section header shows the count, e.g. "Inbox (3)". When the inbox is empty, the entire section (header included) is hidden — no "Inbox (0)".
- Each card shows: the binding color dot, the issue title (truncated to one line), a state badge (In Review / Blocked), and a relative age computed from `COALESCE(last_event_at, updated_at)` (e.g. "12m", "2h").
- Clicking a card navigates to `/{binding_name}?issue={id}` — the existing flyout deep-link (`app/[binding]/page.tsx` already reads the `issue` search param).
- Data via TanStack Query under a `["inbox"]` key with a new `fetchInbox()` in `lib/api.ts`; `refetchInterval` 10s as the polling fallback.
- Live updates: in `QueryProvider.tsx`, on WebSocket `issue.updated` / `issue.created`, update the `["inbox"]` cache — upsert the row when it qualifies for membership, evict it when it does not (e.g. an operator reply flips state to `todo` and the card disappears without a refetch). Simplest correct approach: invalidate `["inbox"]` on those events; direct cache surgery is optional polish.

No dismiss button in this slice (that is #038). Cards leave the Inbox only via state change (reply, manual PATCH).

## Acceptance criteria

- [ ] Alembic revision `0005_inbox_dismissed_at` exists with working `upgrade()`/`downgrade()`; `SCHEMA_SQL` includes `inbox_dismissed_at TIMESTAMP`; `INITIAL_REVISION` is `0005_inbox_dismissed_at`; `python3 -m pytest tests/test_alembic_baseline.py` passes.
- [ ] `GET /api/inbox` returns only `in_review` and `blocked` issues, across multiple bindings, sorted by `COALESCE(last_event_at, updated_at) DESC, id DESC`; excludes archived-binding issues; requires auth (401/403 when unauthenticated, matching existing endpoints).
- [ ] API test proves a row with `inbox_dismissed_at >= last_event_at` is excluded and a row with `inbox_dismissed_at < last_event_at` is included (seed values directly in the test DB).
- [ ] Sidebar renders the Inbox section below Bindings with count header; section absent from the DOM when the inbox is empty (Playwright asserts both states).
- [ ] Card shows binding dot, truncated title, state badge, relative age; clicking navigates to `/{binding}?issue={id}` and opens the flyout (Playwright).
- [ ] Posting an operator reply to an inboxed issue removes its card without a manual page reload (Playwright, via live update or refetch).
- [ ] Full backend and e2e suites pass.

## Verification

```
cd /home/james/symphony && uv run pytest
cd /home/james/symphony/web/frontend && pnpm test:e2e
```

## Blocked by

None - can start immediately
