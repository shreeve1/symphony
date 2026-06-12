---
id: 038
title: Podium Inbox — dismiss endpoint, card dismiss button, resurface-on-activity
status: pending
blocked_by: [037]
parent: null
priority: 0
created: 2026-06-12
---

## What to build

Dismissal for Inbox cards (read path shipped in #037). Dismissing hides the card from the Inbox without touching the issue's state — the issue stays in its board column. A dismissed card resurfaces automatically when the issue sees new activity.

**Dismiss endpoint.** `POST /api/issues/{id}/dismiss` in `web/api/main.py`:

- Sets `inbox_dismissed_at` to now (use the existing monotonic timestamp helper for consistency) and bumps `updated_at`.
- Guard: 409 unless current state is `in_review` or `blocked` (single atomic UPDATE with a WHERE state guard, mirroring the reply endpoint's pattern at `web/api/main.py:840-851`); 404 for unknown issue.
- Publishes `issue.updated` on the WebSocket hub with the updated row, so other tabs/devices drop the card live.
- No request body. Returns the updated issue row.

**Resurface rule.** Any write that transitions an issue **into** `in_review` or `blocked` must also set `inbox_dismissed_at = NULL`. This is the authoritative resurface mechanism — it covers the blocked-reconciler edge where `in_review → blocked` happens without a run finishing (so `last_event_at` is not bumped and the #037 timestamp-comparison filter alone would keep the card hidden). Apply it at every such write site:

- `tracker_podium.py` `transition_state()` (scheduler verdict transitions and `_block_issue` path).
- `PATCH /api/issues/{id}` when the patch sets `state` to `in_review` or `blocked`.

Transitions into other states (`todo`, `running`, `done`, `archived`) leave `inbox_dismissed_at` untouched.

**Frontend.** On each Inbox card (Sidebar.tsx):

- Small dismiss button (check icon) revealed on card hover — hover-reveal guards against fat-finger dismissal of an unread Blocked card. Always-visible on touch is acceptable fallback.
- Click calls the dismiss endpoint and removes the card optimistically; on error, restore the card. Clicking dismiss must not trigger the card's navigation.
- Add `dismissIssue(id)` to `lib/api.ts`; invalidate/update the `["inbox"]` cache on success.

## Acceptance criteria

- [ ] `POST /api/issues/{id}/dismiss` sets `inbox_dismissed_at`, bumps `updated_at`, returns the updated row, and publishes `issue.updated` (API test asserts the WS broadcast, following `test_websocket.py` patterns).
- [ ] Dismiss returns 409 when the issue state is not `in_review`/`blocked`, and 404 for a nonexistent id.
- [ ] After dismiss, `GET /api/inbox` no longer returns the issue (API test).
- [ ] Resurface via run activity: a dismissed issue whose run projection later writes a newer `last_event_at` reappears in `GET /api/inbox` (API test seeding the projection update).
- [ ] Resurface via transition: `transition_state()` into `in_review` or `blocked`, and a `PATCH` setting state to `in_review`/`blocked`, each clear `inbox_dismissed_at` (tests at both write sites); transitions to other states leave it untouched.
- [ ] Playwright: hovering an Inbox card reveals the dismiss button; clicking it removes the card without navigating, and the issue remains visible in its board column.
- [ ] Full backend and e2e suites pass.

## Verification

```
cd /home/james/symphony && python3 -m pytest
cd /home/james/symphony/web/frontend && pnpm test:e2e
```

## Blocked by

- Blocked by #037
