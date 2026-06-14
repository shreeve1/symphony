# Session Capture: Podium board drag-to-column issue moves

- Date: 2026-06-14
- Purpose: Implement the unimplemented half of issue #18 ("change the status **or column** to archive nothing happens") — drag-to-column on the Podium Kanban board.
- Scope: Frontend-only feature work + e2e test. The archive bug itself was already fixed by migration 0008 (separate, prior work).

## Durable Facts

- Before this change, `KanbanBoard.tsx` wrapped the board in a placeholder `<DndContext>` with no drag handlers, so dragging a card did nothing; only the state-chip path changed an issue's state. — Evidence: commit `a4ea162`, prior `web/frontend/components/KanbanBoard.tsx`
- The board reads its cards from the React Query cache `["issues", binding]` (populated in `app/[binding]/page.tsx` via `fetchBindingIssues`, refreshed by `refetchInterval` polling **and** by the `issue.updated` WebSocket upsert in `QueryProvider.tsx`). The board does not own a separate copy of the issue list. — Evidence: `web/frontend/app/[binding]/page.tsx`, `web/frontend/components/QueryProvider.tsx`
- The server `PATCH /api/issues/{id}` handler (`patch_issue`) applies **no run-state gating** for `state` transitions — any of the six states is accepted regardless of `latest_run_state`. The only state-conditional behavior is archive teardown (`_maybe_teardown_archived_worktree` when `state→archived` and no active run) and the done FF-merge. So dragging a `running` card is allowed by the server; no client-side block was added. — Evidence: `web/api/main.py` `patch_issue` (~:975-1057)
- `state` is in `NON_NULLABLE_FIELDS`; a drop always sends a concrete target state, never null. — Evidence: `web/api/main.py:557`

## Decisions

- Drag persists via the same `patchIssue(id, { state })` call the state chip uses — one persistence path, not a new endpoint. — Evidence: commit `2e75d83`
- Click-vs-drag disambiguation uses dnd-kit `PointerSensor` with `activationConstraint: { distance: 5 }`, so a tap stays a click (opens the flyout) and only a real drag starts a move. — Evidence: `web/frontend/components/KanbanBoard.tsx`
- Optimistic update rewrites the `["issues", binding]` query cache on drop and rolls back on PATCH failure; the incoming `issue.updated` WS event upserts the same row by id, so optimistic + live reconcile is idempotent (no double-move). — Evidence: `web/frontend/components/KanbanBoard.tsx`
- Both column render branches (expanded panel and collapsed rail) are `useDroppable` targets keyed by the column's state, so a drop onto a collapsed column's rail still moves the card. Dropping onto **Archived** is a real archive (engine-terminal teardown), accepted with eyes open. — Evidence: `web/frontend/components/KanbanBoard.tsx`
- `@dnd-kit/sortable` and `@dnd-kit/utilities` were **not** added (within-column reordering is out of scope; `utilities` is not hoisted under pnpm, so the DragOverlay pattern avoids needing a transform helper). — Evidence: `web/frontend/package.json`

## Evidence

- `web/frontend/components/IssueCard.tsx` — gained optional drag props (`dragRef`, `dragListeners`, `dragAttributes`, `isDragging`); renders plain/clickable when omitted (the DragOverlay clone).
- `web/frontend/components/KanbanBoard.tsx` — sensors, `Column` (useDroppable) + `DraggableCard` (useDraggable) wrappers, `onDragStart`/`onDragEnd`, `DragOverlay`, optimistic `useMutation`.
- `web/frontend/tests/board-dnd.spec.ts` — e2e: drag-persist path (mousedown→incremental mousemove past 5px→mouseup) and the click-still-opens-flyout guard. Both pass.
- `npx tsc --noEmit` clean; `npx playwright test board-dnd.spec.ts` 2 passed.

## Exclusions

- No secrets, env values, or `/home/james/symphony-host.env` contents.
- `claude_runner.py` working-tree change (orphan-reaper ownership guard) was present but is unrelated to this work and was left untouched/uncommitted.

## Open Questions And Follow-Ups

- `board.spec.ts:4` (backdrop click at `{5,5}` to close the flyout) is a **pre-existing failure**, reproduced with this session's files stashed — the sidebar "Podium" link intercepts the click. Unrelated to drag work; not fixed here.
- Frontend changes are committed but **not deployed**: podium-web must be rebuilt + restarted via `web/frontend/deploy.sh` (atomic staging swap) to serve them. Ask James before any service action.
- Within-column reordering (`@dnd-kit/sortable`) remains deferred.
