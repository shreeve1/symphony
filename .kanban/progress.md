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
