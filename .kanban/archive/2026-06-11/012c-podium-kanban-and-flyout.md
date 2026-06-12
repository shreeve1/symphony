---
id: 012c
title: Podium kanban board + issue flyout with Comments/Context tabs
status: done
blocked_by: [012b]
parent: null
priority: 0
created: 2026-06-10
---

## What to build

Complete the Phase 1 prototype UI. Adds the kanban board, the clickable
issue flyout, the Comments/Context tabs, and dnd-kit set up for future
drag-drop (unused in this slice).

Frontend additions:

- `/{binding}` page replaces the placeholder from #012b with a real
  Kanban board: five columns (`Todo / In Review / Running / Blocked / Done`),
  each rendering issue cards from `/api/bindings/{name}/issues`.
- Issue card shows: title, priority badge, latest verdict pill, age
  ("30s ago" style timestamp from `last_event_at`).
- Click card → side flyout slides in from the right (~480px wide).
- Flyout contents:
  - Title (read-only) + description (read-only markdown).
  - Metadata chips row: `state`, `preferred_skill`, `preferred_agent`,
    `preferred_model`, `priority`, `worktree_active`. Chips are display-only
    in this slice (editing lands in #013).
  - Two tabs: **Comments** (renders `comments_md` as markdown) and
    **Context** (renders `context_md` as markdown).
  - Run history list below: each run row shows verdict, model, started_at.
- dnd-kit installed and imported in `KanbanBoard.tsx` but no drag handlers
  wired yet (placeholder for a later slice).

Files:
- `web/frontend/components/KanbanBoard.tsx`
- `web/frontend/components/IssueCard.tsx`
- `web/frontend/components/IssueFlyout.tsx`
- `web/frontend/components/RunHistoryList.tsx`
- `web/frontend/tests/board.spec.ts` — visits `/trading`, asserts five
  columns render, asserts at least one card visible, clicks card,
  asserts flyout opens.
- `web/frontend/tests/flyout-tabs.spec.ts` — opens flyout, switches
  between Comments and Context tabs, asserts each renders the expected
  text from the seeded issue.

Cost field: do NOT render `cost_usd` anywhere in the UI. Run history shows
verdict + model + started_at only. The column exists in the DB for #016
detail view but Phase 1 hides it (per grilling decision to drop cost
visualization).

## Acceptance criteria

- [x] `/{binding}` renders five Kanban columns in fixed order: Todo, In Review, Running, Blocked, Done.
- [x] Each issue card renders title + priority badge + verdict pill + age.
- [x] Clicking a card opens the flyout; clicking outside closes it.
- [x] Flyout shows title, description, all six metadata chips, two tabs.
- [x] Comments tab renders the seeded `comments_md` markdown.
- [x] Context tab renders the seeded `context_md` markdown.
- [x] Run history list renders at least one run with verdict + model + started_at — no `$` cost rendered (assert `data-testid="run-cost"` is absent).
- [x] dnd-kit imported in `KanbanBoard.tsx` (assert via grep of source).
- [x] Playwright `board.spec.ts` and `flyout-tabs.spec.ts` both pass via `pnpm test:e2e`.

## Verification

```
cd /home/james/symphony && uv run pytest && \
cd web/frontend && pnpm test:e2e
```

## Implementation notes

- Shipped in commit `9d930b1` (`feat(web): Podium kanban board + issue flyout (#012c)`).
- Deviation from spec: the flyout is resizable from its left edge with the
  chosen width persisted to `localStorage` (default 480px, clamped 360–900px).
  The spec's "~480px wide" became the default rather than a fixed width —
  validated via a UI prototype before the build.
- Beyond spec, also added for robustness after independent review: dialog/tab
  ARIA roles, focus move-in/restore, Escape-to-close, and error/loading
  branches on the detail and runs queries.

## Blocked by

- #012b (frontend shell + sidebar must exist before board layers on it)
