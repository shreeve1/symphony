---
title: Podium issue archive ("delete button") design
type: analysis
status: promoted
created: 2026-06-12
updated: 2026-06-12
sources:
  - wiki/raw/sessions/2026-06-12-issue-archive-state-design.md
  - CONTEXT.md
  - web/api/schema.py
  - web/api/main.py
  - tracker_podium.py
  - scheduler.py
  - web/api/tests/test_worktree_api.py
  - tests/test_trading_podium_dispatch.py
  - web/frontend/lib/issues.ts
confidence: medium
tags: [podium, archive, board-ui, retention, design-decision]
---

# Podium issue archive ("delete button") design

Design accepted 2026-06-12 in a grill-me session. #034 implemented the schema/API/UI portion: `archived` is now a sixth Issue state, `GET /api/bindings/{name}/issues?state=archived` filters server-side, the Archived board column renders rightmost and defaults collapsed, and `IssueFlyout` has a no-confirm Archive button [source: .kanban/issues/034-podium-archived-state-core.md] [source: web/api/schema.py] [source: web/api/main.py] [source: web/frontend/lib/issues.ts] [source: web/frontend/components/IssueFlyout.tsx]. #035 implemented engine-terminal handling: `transition_state` no-ops for archived issues, idle archive PATCH tears down issue worktrees, and run completion logs `archived_terminal` before skipping verdict state transitions and tearing down deferred worktrees [source: .kanban/issues/035-podium-archive-engine-terminal-contract.md] [source: tracker_podium.py] [source: web/api/main.py] [source: scheduler.py]. Retention purge (#036) remains pending. The design resolves how Podium disposes of junk issues without overloading Done — Done is load-bearing for infra issues with `worktree_active` (PATCH to done fires FF-merge + teardown) [source: web/api/main.py#L750].

## Decisions

| Area | Decision |
|---|---|
| Semantics | Archive, not hard delete |
| Representation | Sixth `state` value `archived`; no new column (James's constraint). CHECK-constraint change = SQLite table-rebuild Alembic migration [source: web/api/schema.py#L31] |
| Engine contract | Archived is never an engine Role. Engine never selects archived work; post-run honors archived as terminal: no verdict state transition, worktree torn down, output discarded [source: CONTEXT.md#tracker-contract] [source: scheduler.py] |
| Mid-run archive | Allowed; session runs to completion; deferred worktree teardown at run completion via `remove_worktree` [source: web/api/worktree.py#L83] [source: scheduler.py]. Coding bindings: agent keeps committing to bound checkout until session end; commits stay (accepted) |
| Board UI | General per-column minimize (−/+ collapse to strip) on all columns; archived column rightmost; collapse state in localStorage per binding; archived collapsed by default |
| Button | "Archive" button in IssueFlyout near metadata chips, no confirm; state chip is the restore path. Card-hover affordance deferred |
| Retention | Purge from day one: opportunistic sweep on archive PATCH + API startup; `state='archived' AND updated_at < now − 14 days` (hardcoded); delete order null `latest_run_id` → delete runs → delete issue, one transaction; best-effort unlink run `log_path` files |

## Why sixth state beat a flag column

The board, counts, and flyout state chip all derive from the `STATES` array [source: web/frontend/lib/issues.ts#L5], so a sixth state propagates through the UI automatically once the minimize feature exists; a flag column would have needed pseudo-column synthesis, count exclusions, a new PATCH field, and an `AND NOT archived` in scheduler todo-polling. Cost accepted with eyes open: table-rebuild migration, archiving forgets prior state, and the glossary line weakened from "engine never reads archived" to "engine never selects archived work; post-run honors it as terminal."

## Hazards identified

- **Resurrection bug (fixed by #035)**: `transition_state` now guards issue state writes with `state != 'archived'`, so a run finishing after operator archive cannot overwrite `archived` [source: tracker_podium.py].
- **FK order for purge**: `PRAGMA foreign_keys = ON` plus `run.issue_id` and `issue.latest_run_id` FKs force the null→runs→issue delete order [source: web/api/db.py#L51].
- **Terminology collision**: code already says "archive" for worktrees (`_maybe_archive_worktree`, "Worktree archived" [source: web/api/main.py#L949]); consider rewording during implementation.

## Follow-ups

- Retention purge (#036): hard-delete archived issues after 14 days with FK-safe run/log cleanup.
- Card-hover archive affordance (separate work).
- Purge/log-unlink coexistence with #022's 90-day/100-log retention.
- ADR offered for archived-as-state; declined.
