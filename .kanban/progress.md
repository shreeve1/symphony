# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

## #016 Podium — Run detail + history view — 2026-06-11

**What changed:** Added run detail API endpoints, 1MB tail-log serving, clickable run rows, stacked frontend detail flyout, log reload button, and regression coverage.
**Files:** web/api/main.py, web/api/tests/test_run_endpoints.py, web/frontend/lib/api.ts, web/frontend/components/IssueFlyout.tsx, web/frontend/components/RunHistoryList.tsx, web/frontend/components/RunDetailPanel.tsx, web/frontend/tests/run-detail.spec.ts
**Decisions:** Kept `cost_usd` in the fetched API shape but omitted it from rendered metadata, matching the prior cost-visualization decision.
**Conventions established:** Run log fetch treats 404 `log_not_found` as an empty-log UI state.
**Notes for next iteration:** Run detail fetches `skill_invoked` through the full-row endpoint but does not render it because the acceptance metadata grid omitted it.

## #017 Podium WebSocket — live Issue + Run state updates — 2026-06-11

**What changed:** Added `WS /api/ws`, in-process fanout, issue mutation events, seeded-run placeholder events, WebSocket-driven frontend cache updates, reconnect/refetch behaviour, and disconnect pill coverage.
**Files:** pyproject.toml, uv.lock, web/api/main.py, web/api/seed.py, web/api/tests/test_websocket.py, web/frontend/app/layout.tsx, web/frontend/components/NewIssueModal.tsx, web/frontend/components/QueryProvider.tsx, web/frontend/playwright.config.ts, web/frontend/tests/live-sync.spec.ts
**Decisions:** Kept last-write-wins semantics for concurrent issue edits; no version column or conditional PATCH in this slice. Added `websockets` runtime dependency because uvicorn needs a WebSocket protocol implementation.
**Conventions established:** Podium live updates use one browser-session WebSocket connection, in-process API fanout, and TanStack Query cache updates/refetches instead of HTTP polling.
**Notes for next iteration:** #020 can publish real `run.updated` events when engine Run rows mutate; #023a must keep uvicorn at `--workers 1` for in-process fanout correctness.

## #018 Podium auth — bcrypt shared password + localhost binding — 2026-06-11

**What changed:** Added bcrypt-backed shared-password auth, signed httpOnly `podium_session` cookies, failed-login throttling, `/api/auth/login|logout|whoami`, API and WebSocket auth gates, frontend login/logout shell, and `podium set-password` CLI helper.
**Files:** pyproject.toml, uv.lock, web/api/auth.py, web/api/main.py, web/api/tests/test_auth.py, web/api/tests/conftest.py, web/cli/podium.py, web/cli/tests/test_skills_refresh.py, web/frontend/components/AppShell.tsx, web/frontend/app/login/page.tsx, web/frontend/lib/api.ts, web/frontend/playwright.config.ts, web/frontend/tests/auth.spec.ts, web/frontend/tests/fixtures.ts
**Decisions:** Dev/test auth uses seeded `secret` only inside tests; production secrets remain env-only via `PODIUM_PASSWORD_HASH` and `PODIUM_SESSION_SECRET`. `.env` loading is read-only and never writes secrets to disk.
**Conventions established:** Frontend e2e specs authenticate with `page.request.post('/api/auth/login')`; unauthenticated coverage belongs in `auth.spec.ts`. Podium WebSocket connections require the same signed session cookie as protected HTTP API routes.
**Notes for next iteration:** `pnpm lint` still prompts because ESLint is not configured; use `pnpm exec tsc --noEmit` for frontend typecheck until lint config lands.

## #025 prompt_renderer Podium path + Skill→Mode projection — 2026-06-11

**What changed:** Added `tracker_kind="podium"` rendering, Podium issue payload fields (`comments_md`, `context_md`, `preferred_skill`), non-truncating Podium comments, dedicated Issue Context rendering, and `skill_mode_map.SKILL_TO_MODE`/`mode_for_skill(...)`.
**Files:** prompt_renderer.py, skill_mode_map.py, tests/test_prompt_renderer_podium.py
**Decisions:** Kept Plane default behavior unchanged; Podium maps known preferred Skills back to legacy Mode only inside the renderer bridge. Unknown or missing Skills project to `execute`.
**Conventions established:** `skill_mode_map.py` is the transitional single source for Skill→Mode projection until Podium fully retires Mode.
**Notes for next iteration:** #019 should call `render_prompt(..., tracker_kind="podium")` with Podium issue rows populated from SQLite. LSP currently reports stale `skill_mode_map` missing-import noise despite tracked file, runtime import, py_compile, and pytest passing.

## #019 Tracker Adapter (Podium) — engine reads/writes Podium store — 2026-06-11

**What changed:** Added `tracker: plane|podium` binding config, runtime-checkable tracker protocol, `PodiumTrackerAdapter`, WAL/busy-timeout SQLite connections, scheduler context appends for Podium, and regression tests for method parity, concurrent writers, and mocked engine dispatch.
**Files:** config.py, main.py, plane_adapter.py, scheduler.py, tracker_adapter.py, tracker_podium.py, web/api/db.py, tests/test_config.py, tests/test_tracker_podium.py, tests/test_podium_sqlite_concurrent.py, tests/test_engine_against_podium.py
**Decisions:** Podium coding bindings project state roles to `issue.state`, mode roles from `preferred_skill`, and agent roles from `preferred_agent`; labels are intentionally no-op/dropped in Podium.
**Conventions established:** `tracker_podium.py` must not directly import `plane_adapter`; shared Plane compatibility types stay outside the Podium adapter path.
**Notes for next iteration:** Infra-binding approval/schedule projection remains deferred to #023c. #020 can flip a test/cutover binding to `tracker: podium` without touching live bindings first.


## #020 Engine dispatch end-to-end against Podium — trading cutover — 2026-06-11

**What changed:** Cut `trading` over to `tracker: podium`, added scheduler Run-row lifecycle recording, wrote per-run stdout/stderr logs, captured cost/token markers, appended Podium comments/context, added rollback docs, and covered the happy path with a mocked Pi dispatch test.
**Files:** bindings.yml, scheduler.py, tracker_podium.py, web/README.md, tests/test_trading_podium_dispatch.py
**Decisions:** Terminal Podium Run state uses existing schema values (`succeeded`/`failed`) while the issue remains `in_review`; `latest_verdict` carries `done`/`review`/`blocked`.
**Conventions established:** Podium run logs are written beside the Podium DB in tests and under `/var/lib/symphony/runs` in production; Pi may emit `SYMPHONY_COST_USD`, `SYMPHONY_INPUT_TOKENS`, and `SYMPHONY_OUTPUT_TOKENS` markers for Run metadata.
**Notes for next iteration:** Manual service restart and operator smoke remain outside Ralph automation and still require explicit approval at the moment of action.

## #020 Blocker update — 2026-06-11

**What changed:** Reopened #020 as blocked after automated implementation and review because the live operator cutover smoke was not performed in this session.
**Files:** .kanban/issues/020-podium-trading-cutover.md
**Decisions:** Automated lifecycle coverage is not a substitute for the issue's operator-driven Podium smoke criterion.
**Conventions established:** Ralph may finish #020 as BLOCKED when code passes but the remaining acceptance criterion requires explicit operator restart/smoke confirmation.
**Notes for next iteration:** Ask James for restart approval, then file/observe the Podium smoke; if it passes, mark the remaining smoke criterion done.

## #020 Cutover smoke complete — 2026-06-11

**What changed:** Performed the operator-approved trading→Podium cutover smoke and closed #020 as done. Found and fixed a live dispatch bug surfaced by the first real run.
**Files:** tracker_podium.py, tests/test_trading_podium_dispatch.py, .kanban/issues/020-podium-trading-cutover.md
**Root cause:** `PodiumTrackerAdapter.db_path` was `None` in production (constructed without it by `main._build_binding_runtime`), so `_start_run_record` fell back to the unwritable `RUN_LOG_ROOT` (`/var/lib/symphony/runs`). `_write_run_log` then raised `PermissionError`, crashing `_finish_run_record` — runs never finalized; issues reached In Review only via the stale-running reconciler.
**Fix:** Resolve `db_path` in `__post_init__` so the run-log root co-locates with the resolved DB (commit `8eb4aa6`). Added `test_trading_podium_dispatch_logs_colocate_with_resolved_db`, which builds the adapter as `main` does (no `db_path`, no `RUN_LOG_ROOT` override) and fails without the fix.
**Decisions:** The mocked dispatch test masked the bug by passing an explicit `db_path` AND monkeypatching `RUN_LOG_ROOT`; regression coverage must exercise the production construction path.
**Conventions established:** Podium run logs live beside the active `podium.db` (`<db parent>/runs/<id>.log`), not at the `/var/lib/symphony/runs` default, until/unless a writable `/var/lib/symphony` exists.
**Notes for next iteration:** Podium web UI/API was not running, so the smoke was filed by direct `podium.db` insert. Seed issue 3 / run 5 are left in a stale state (run 5 stuck `running`) from the pre-fix crash — cosmetic seed noise, safe to clean later. Commits `12289da` and `8eb4aa6` are local-only (not pushed to `github-personal`).

## #021 Worktree opt-in + auto-merge on Done — 2026-06-11

**What changed:** Added persistent per-Issue Podium worktrees, dispatch-time worktree cwd selection, FF-only merge-on-Done cleanup, blocked comments for merge aborts, toggle-off archive comments, UI worktree path chips, and regression/e2e coverage.
**Files:** agent_runner.py, plane_adapter.py, tracker_podium.py, web/api/worktree.py, web/api/main.py, tests/test_agent_runner.py, web/api/tests/test_worktree.py, web/api/tests/test_worktree_api.py, web/frontend/components/IssueFlyout.tsx, web/frontend/components/RunDetailPanel.tsx, web/frontend/tests/worktree.spec.ts
**Decisions:** Podium-owned nested `worktrees/` directories are ignored by the dirty-base precheck, but other untracked files still block auto-merge. Merge always checks out `base_branch` before `git merge --ff-only`.
**Conventions established:** `worktree_active=true` creates/reuses `worktrees/<binding>/<issue_id>` on dispatch and branch `podium/<binding>/<issue_id>`; state→Done performs FF-only merge and teardown, while abort paths leave the worktree intact and move the issue to Blocked with an operator-facing comment.
**Notes for next iteration:** Full verification passed: `uv run pytest` (545 passed, 1 skipped) and `pnpm test:e2e` (15 passed). The local `.env` can mask missing auth env in tests; auth tests now monkeypatch dotenv loading for the missing-secret startup case.
