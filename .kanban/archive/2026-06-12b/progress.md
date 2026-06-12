# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.


## #028 Podium — models.yml catalog + searchable dropdowns — 2026-06-12

**What changed:** Added repo-root `models.yml`, backend model catalog validator/loader, `/options` model-object response shape, typed frontend `ModelOption`, searchable new-issue comboboxes, agent-filtered model choices, and regression/e2e coverage.
**Files:** `models.yml`, `web/api/main.py`, `web/api/tests/test_issue_create.py`, `web/frontend/lib/api.ts`, `web/frontend/components/NewIssueModal.tsx`, `web/frontend/tests/new-issue.spec.ts`.
**Decisions:** Model catalog is git-tracked YAML authored config; `preferred_model` and `preferred_agent` stay free-text end to end, while Skill remains selection-only because backend FK validation still applies.
**Conventions established:** `/api/bindings/{name}/options` returns `models` as `{id, agent, label?, provider?}` objects loaded through `_validate_models`; missing or invalid `models.yml` degrades to an empty model list without failing the endpoint.
**Notes for next iteration:** #032 should reuse `_validate_models()` for the `symphony-models` skill instead of reimplementing catalog validation.

## #029 Podium — gated interval polling for engine-driven state freshness — 2026-06-12

**What changed:** Added shared frontend polling helpers, active-aware board refetch intervals, run/log detail refetch intervals, and direct-SQLite Playwright coverage proving polling without WebSocket fanout.
**Files:** `web/frontend/lib/polling.ts`, `web/frontend/app/[binding]/page.tsx`, `web/frontend/components/RunDetailPanel.tsx`, `web/frontend/tests/fixtures.ts`, `web/frontend/tests/live-sync.spec.ts`.
**Decisions:** Engine-driven state freshness remains frontend polling per ADR-0006; WebSocket behavior stays unchanged for API-process optimistic updates.
**Conventions established:** Use `issue.state === "running"` or `latest_run_state in {"queued", "running"}` for board activity; use Run `state in {"queued", "running"}` for Run detail/log polling.
**Notes for next iteration:** #030 can rely on Run detail refetch-on-terminal behavior and only needs elapsed timer rendering/hand-off.

## #030 Podium — run liveness elapsed timer + refresh-on-exit — 2026-06-12

**What changed:** Added shared Run duration helpers, ticking elapsed timers in the Run detail panel, running indicators in Run history rows, and Playwright coverage for timer advancement plus terminal handoff.
**Files:** `web/frontend/lib/run-duration.ts`, `web/frontend/components/RunDetailPanel.tsx`, `web/frontend/components/RunHistoryList.tsx`, `web/frontend/tests/live-sync.spec.ts`.
**Decisions:** Active runs render as `running <elapsed>` while terminal runs use final wall-clock duration from `started_at`/`ended_at`; #029 polling remains the refresh-on-exit mechanism.
**Conventions established:** Use `isLiveElapsedRun()` and `formatRunDuration()` for queued/running Run liveness affordances instead of local duration formatting.
**Notes for next iteration:** #031 dashboard should continue keying board-level state counts off `issue.state`; active-run liveness now lives in run-specific UI only.

## #031 Podium — board-level overview dashboard — 2026-06-12

**What changed:** Replaced the root placeholder with a cross-binding dashboard, global roll-up, per-binding state summary cards, last-activity display, and a cross-binding attention list for blocked/failed issues.
**Files:** `web/frontend/app/page.tsx`, `web/frontend/app/[binding]/page.tsx`, `web/frontend/components/KanbanBoard.tsx`, `web/frontend/tests/dashboard.spec.ts`, plus selector updates in existing Playwright specs.
**Decisions:** Dashboard aggregation stays client-side from the existing issue-list payload; no backend aggregate endpoint was introduced for two active bindings.
**Conventions established:** Board-level status counts continue to use `issue.state`; attention rows deep-link via `/<binding>?issue=<id>` and flyout close clears the query parameter.
**Notes for next iteration:** #032 can proceed from the #028 model catalog validator; dashboard work did not change skill/model catalog contracts.

## #032 symphony-skills + symphony-models catalog maintenance skills — 2026-06-12

**What changed:** Added repo-local operator skill docs for refreshing the Podium Skill catalog and maintaining the git-tracked model catalog, plus regression coverage for the documented contracts.
**Files:** `.claude/skills/symphony-skills/SKILL.md`, `.claude/skills/symphony-models/SKILL.md`, `tests/skills/test_catalog_maintenance_skills.py`, `.kanban/issues/032-symphony-skills-and-models-maintenance-skills.md`.
**Decisions:** `symphony-models` stays doc-driven and reuses `web.api.main._load_models()` / `_validate_models()` instead of adding bespoke add/remove code.
**Conventions established:** Catalog maintenance skills must document no service restart, no Plane API calls, no env-file reads, and no secret printing.
**Notes for next iteration:** Full `tests/skills/` coverage remains the verification gate for repo-local `symphony-*` skill docs.

## #033 Podium — per-column board minimize with localStorage persistence — 2026-06-12

**What changed:** Added minimize/expand controls to every board column, collapsed-column strips with live counts, per-binding `podium.collapsed.<binding>` persistence with corrupt-value fallback, Playwright e2e isolation via `NEXT_DIST_DIR=.next.e2e`, and board-minimize e2e coverage.
**Files:** `web/frontend/components/KanbanBoard.tsx`, `web/frontend/playwright.config.ts`, `web/frontend/.gitignore`, `web/frontend/tests/board-minimize.spec.ts`, `.kanban/issues/033-podium-board-column-minimize.md`.
**Decisions:** Column collapse state stores state keys as a JSON array per binding; missing or invalid storage falls back to all columns expanded for #033.
**Conventions established:** Frontend e2e must run Next dev against `.next.e2e` so tests do not clobber the production `.next` served by `podium-web.service`.
**Notes for next iteration:** #034 can add the `archived` state and then set archived-column default-collapse behavior on top of this collapse mechanism.

## #034 Podium — sixth archived issue state — 2026-06-12

**What changed:** Added Alembic/runtime schema support for `archived`, API state validation/filter coverage, reply-guard regression coverage, rightmost Archived board column, default-collapsed archived column behavior, flyout Archive button, and archive/restore e2e coverage.
**Files:** `web/api/migrations/versions/0004_archived_state.py`, `web/api/schema.py`, `web/api/main.py`, `web/api/tests/test_issue_patch.py`, `web/api/tests/test_reply.py`, `web/frontend/lib/issues.ts`, `web/frontend/components/KanbanBoard.tsx`, `web/frontend/components/IssueFlyout.tsx`, `web/frontend/tests/archive.spec.ts`, `web/frontend/tests/board.spec.ts`, `.kanban/issues/034-podium-archived-state-core.md`.
**Decisions:** `archived` is visible in Podium UI but remains outside reply redispatch states; live DB migration/application stays an operator step outside this slice.
**Conventions established:** New bindings with no collapse localStorage default to `archived` collapsed; existing stored collapse sets are respected.
**Notes for next iteration:** #035 must make archived engine-terminal; #036 can implement 14-day purge after #034.

## #035 Podium — archived is engine-terminal — 2026-06-12

**What changed:** Added the archived terminal engine guard, idle archive worktree teardown, deferred mid-run archive teardown, and regression coverage for run finalization plus merge-on-done preservation.
**Files:** `tracker_podium.py`, `web/api/main.py`, `scheduler.py`, `tests/test_tracker_podium.py`, `web/api/tests/test_worktree_api.py`, `tests/test_trading_podium_dispatch.py`, `.kanban/issues/035-podium-archive-engine-terminal-contract.md`.
**Decisions:** Archived issues still receive completed Run rows, verdicts, summaries, comments, and context projections, but `issue.state` is terminal and never resurrected by post-run verdict transitions.
**Conventions established:** Scheduler logs `archived_terminal issue_id=<id> run_id=<id>` when it skips a verdict transition because an issue was archived mid-run; idle archive PATCH removes persistent worktrees immediately, while active runs defer teardown to completion.
**Notes for next iteration:** #036 can assume archived issues are terminal and worktrees should normally already be gone, but purge still needs defensive worktree removal for drift.

## #036 Podium — 14-day archived-issue retention purge — 2026-06-12

**What changed:** Added archived-issue purge sweeps at API startup and after archive PATCH transitions, deleting eligible issues older than 14 days with FK-safe per-issue transactions, post-commit run-log unlink, structured purge logging, and defensive worktree cleanup.
**Files:** `web/api/main.py`, `web/api/tests/test_archive_purge.py`, `.kanban/issues/036-podium-archived-retention-purge.md`.
**Decisions:** Purge uses hardcoded `PURGE_AFTER_DAYS = 14` and `updated_at` as the archive-age clock; no deletion WebSocket event is emitted, so purged issues disappear on next fetch.
**Conventions established:** Archive purge is opportunistic API-process maintenance, not scheduler work; cleanup must check actual worktree existence, not only `worktree_active`, because purge also repairs drift.
**Notes for next iteration:** No more archive-design issues remain pending on the local Ralph board.
