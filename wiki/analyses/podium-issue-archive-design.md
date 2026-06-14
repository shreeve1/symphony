---
title: Podium issue archive ("delete button") design
type: analysis
status: promoted
created: 2026-06-12
updated: 2026-06-14
sources:
  - wiki/raw/sessions/2026-06-12-issue-archive-state-design.md
  - wiki/raw/sessions/2026-06-13-remove-flyout-archive-button.md
  - CONTEXT.md
  - .kanban/issues/036-podium-archived-retention-purge.md
  - web/api/schema.py
  - web/api/main.py
  - tracker_podium.py
  - scheduler.py
  - web/api/tests/test_worktree_api.py
  - web/api/tests/test_archive_purge.py
  - tests/test_trading_podium_dispatch.py
  - web/frontend/lib/issues.ts
  - web/frontend/components/KanbanBoard.tsx
  - web/frontend/components/IssueCard.tsx
  - web/frontend/tests/board-dnd.spec.ts
  - wiki/raw/sessions/2026-06-14-board-drag-to-column.md
confidence: high
tags: [podium, archive, board-ui, retention, design-decision]
---

# Podium issue archive ("delete button") design

Design accepted 2026-06-12 in a grill-me session. #034 implemented the schema/API/UI portion: `archived` is now a sixth Issue state, `GET /api/bindings/{name}/issues?state=archived` filters server-side, the Archived board column renders rightmost and defaults collapsed, and `IssueFlyout` originally carried a no-confirm Archive button [source: .kanban/issues/034-podium-archived-state-core.md] [source: web/api/schema.py] [source: web/api/main.py] [source: web/frontend/lib/issues.ts] [source: web/frontend/components/IssueFlyout.tsx]. #035 implemented engine-terminal handling: `transition_state` no-ops for archived issues, idle archive PATCH tears down issue worktrees, and run completion logs `archived_terminal` before skipping verdict state transitions and tearing down deferred worktrees [source: .kanban/issues/035-podium-archive-engine-terminal-contract.md] [source: tracker_podium.py] [source: web/api/main.py] [source: scheduler.py]. #036 implemented retention purge: API startup and post-archive PATCH sweeps hard-delete archived issues older than 14 days, delete dependent Run rows FK-safely, unlink run logs best-effort, and remove lingering worktrees including stale `worktree_active = FALSE` drift [source: .kanban/issues/036-podium-archived-retention-purge.md] [source: web/api/main.py] [source: web/api/tests/test_archive_purge.py]. The design resolves how Podium disposes of junk issues without overloading Done — Done is load-bearing for infra issues with `worktree_active` (PATCH to done fires FF-merge + teardown) [source: web/api/main.py#L750].

## Decisions

| Area | Decision |
|---|---|
| Semantics | Archive, not hard delete |
| Representation | Sixth `state` value `archived`; no new column (James's constraint). CHECK-constraint change = SQLite table-rebuild Alembic migration [source: web/api/schema.py#L31] |
| Engine contract | Archived is never an engine Role. Engine never selects archived work; post-run honors archived as terminal: no verdict state transition, worktree torn down, output discarded [source: CONTEXT.md#tracker-contract] [source: scheduler.py] |
| Mid-run archive | Allowed; session runs to completion; deferred worktree teardown at run completion via `remove_worktree` [source: web/api/worktree.py#L83] [source: scheduler.py]. Coding bindings: agent keeps committing to bound checkout until session end; commits stay (accepted) |
| Board UI | General per-column minimize (−/+ collapse to strip) on all columns; archived column rightmost; collapse state in localStorage per binding; archived collapsed by default |
| Button | ~~"Archive" button in IssueFlyout near metadata chips, no confirm~~ — **removed 2026-06-13** (working tree); archiving now goes through the state chip (`edit-state` select, which already offers `archived` via `STATES`). State chip remains the restore path. Card-hover affordance deferred [source: wiki/raw/sessions/2026-06-13-remove-flyout-archive-button.md] [source: web/frontend/components/IssueFlyout.tsx] |
| Retention | Implemented in #036: opportunistic sweep on archive PATCH + API startup; `state='archived' AND updated_at < now − 14 days` (hardcoded); delete order null `latest_run_id` → delete runs → delete issue, one transaction; best-effort unlink run `log_path` files; defensive worktree cleanup checks actual filesystem state, not only `worktree_active` [source: web/api/main.py] [source: web/api/tests/test_archive_purge.py] |

## Why sixth state beat a flag column

The board, counts, and flyout state chip all derive from the `STATES` array [source: web/frontend/lib/issues.ts#L5], so a sixth state propagates through the UI automatically once the minimize feature exists; a flag column would have needed pseudo-column synthesis, count exclusions, a new PATCH field, and an `AND NOT archived` in scheduler todo-polling. Cost accepted with eyes open: table-rebuild migration, archiving forgets prior state, and the glossary line weakened from "engine never reads archived" to "engine never selects archived work; post-run honors it as terminal."

## Hazards identified

- **Resurrection bug (fixed by #035)**: `transition_state` now guards issue state writes with `state != 'archived'`, so a run finishing after operator archive cannot overwrite `archived` [source: tracker_podium.py].
- **FK order for purge (implemented by #036)**: `PRAGMA foreign_keys = ON` plus `run.issue_id` and `issue.latest_run_id` FKs force the null→runs→issue delete order; #036 regression tests cover rollback when an external FK blocks Run deletion and verify no orphaned runs or nulled `latest_run_id` remain [source: web/api/db.py#L51] [source: web/api/tests/test_archive_purge.py].
- **Terminology collision**: code already says "archive" for worktrees (`_maybe_archive_worktree`, "Worktree archived" [source: web/api/main.py#L949]); consider rewording during implementation.

## Follow-ups

- Card-hover archive affordance (separate work).
- ADR offered for archived-as-state; declined.
- 2026-06-13: flyout Archive button removed (state chip is now the sole archive path); change is in the working tree, not committed/deployed — needs a frontend rebuild + `deploy.sh` staging swap to go live. See C-0164.
- 2026-06-14 (#18): "archive does nothing" reconfirmed as the same CHECK-drift bug fixed by #17's migration `0008_fix_issue_archived_check`; live `podium.db` verified at `alembic_version=0008` with `'archived'` in the `issue.state` CHECK, 81 targeted tests green. No new code needed. **Separate gap:** "change the *column* to archive" by dragging never worked — `KanbanBoard.tsx:4-5` wires dnd-kit as a placeholder with no drag handlers attached for any column; archiving is state-chip-only. Drag-to-column archiving is unimplemented feature work, not a regression [source: web/frontend/components/KanbanBoard.tsx#L4] [source: tickets/18.md].
- 2026-06-14 (#18 follow-up): **drag-to-column gap RESOLVED** (commit `2e75d83`, C-0201). `KanbanBoard` now attaches dnd-kit handlers — `PointerSensor` (5px activation so taps still open the flyout), `useDroppable` per column (expanded panel + collapsed rail, both keyed by state), a `DragOverlay` clone, and an optimistic `patchIssue(id, { state })` against the `["issues", binding]` query cache with rollback (idempotent with the `issue.updated` WS upsert). Dropping onto **Archived** is a real archive (engine-terminal teardown). The server `patch_issue` applies no run-state gating for `state`, so no card is drag-disabled. e2e: `web/frontend/tests/board-dnd.spec.ts`. Committed, **not yet deployed** (needs `deploy.sh` rebuild + restart) [source: web/frontend/components/KanbanBoard.tsx] [source: web/frontend/components/IssueCard.tsx] [source: web/frontend/tests/board-dnd.spec.ts] [source: wiki/raw/sessions/2026-06-14-board-drag-to-column.md].
