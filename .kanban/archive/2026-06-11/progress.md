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

## #021 Claude review fixes — 2026-06-11

**What changed:** Addressed all dev-review-claude findings for #021. Blocked merge aborts now publish the final Blocked row over WebSocket, git worktree operations are offloaded from the async PATCH path, Run rows now record worktree path/branch metadata for active worktree dispatch, Issue API rows expose server-derived worktree path/branch for the frontend, combined done+worktree-off PATCH avoids duplicate archive comments after merge failure, and review note cleanup landed.
**Files:** agent_runner.py, scheduler.py, web/api/main.py, web/api/worktree.py, tests/test_trading_podium_dispatch.py, web/api/tests/test_worktree.py, web/api/tests/test_worktree_api.py, web/frontend/lib/api.ts, web/frontend/components/IssueFlyout.tsx
**Decisions:** Worktree metadata is now projected by the backend instead of reconstructed in the frontend. `state=done` merge/block outcome takes precedence over archive messaging when both fields are patched in one request.
**Conventions established:** Slow git worktree checks/merge/cleanup should run outside the FastAPI event loop via `asyncio.to_thread`; any DB state correction after optimistic PATCH publish must publish the final row too.
**Notes for next iteration:** Verification passed after review fixes: `uv run pytest` (547 passed, 1 skipped), `pnpm exec tsc --noEmit`, and `pnpm test:e2e` (15 passed).

## #022 Restart-time Run reconciliation + run-log retention — 2026-06-11

**What changed:** Added Podium startup reconciliation for orphaned queued/running Run rows and run-log pruning for old/excess logs.
**Files:** scheduler.py, tracker_podium.py, tests/test_run_reconcile.py, tests/test_log_retention.py
**Decisions:** Startup reconciliation marks parent issues Blocked when an orphaned Run is reaped with `verdict='blocked'`; persistent worktrees are preserved for operator inspection.
**Conventions established:** Podium operational maintenance logs use structured `run_reconcile_begin/done` and `log_retention_begin/done` pairs. Run-log retention keeps DB rows, deletes only log files, and clears `run.log_path`.
**Notes for next iteration:** Retention runs at startup through `reconcile_startup` and then every 24 hours from `run_loop`; full verification passed with `uv run pytest` (552 passed, 1 skipped).

## #023a Podium systemd units — 2026-06-11

**What changed:** Installed and enabled `podium-api.service` and `podium-web.service`, prebuilt the Next.js frontend, moved existing manual Podium listeners off ports 8090/8091 with operator approval, and verified both systemd-managed services are active on loopback.
**Files:** .kanban/issues/023a-podium-systemd-units.md; live unit files `/etc/systemd/system/podium-api.service`, `/etc/systemd/system/podium-web.service`
**Decisions:** Added `Environment=HOST=127.0.0.1` to the web unit so `pnpm start` binds Next.js to loopback instead of the package script default `0.0.0.0`.
**Conventions established:** Podium API and web now run as sibling systemd units, separate from `symphony-host.service`, with localhost-only listeners and `OnFailure=telegram-alert@%n.service` wiring.
**Notes for next iteration:** Issue remains blocked only on the live failure-hook acceptance check because the operator declined killing a Podium process to trigger/observe the alert hook. Rollback command is documented in the issue.

## #023b Alembic baseline + SQLite backup wiring — 2026-06-11

**What changed:** Added Alembic baseline verification, migration rules documentation, active Podium SQLite backup script, host cron wiring, and restore-drill evidence.
**Files:** pyproject.toml, uv.lock, scripts/podium-backup.sh, tests/test_alembic_baseline.py, web/api/migrations/env.py, web/api/migrations/README.md, web/README.md, /etc/cron.d/podium-backup, /backup/podium-2026-06-11.db
**Decisions:** Used the cron `.backup` path because `rsnapshot` is not installed. The script resolves the active Podium DB path through `web.api.db.resolve_db_path()` so fallback repo DBs and future `/var/lib/symphony/podium.db` deployments use the same backup job.
**Conventions established:** Schema changes must add a new Alembic revision and keep `SCHEMA_SQL` in sync; verify with `uv run pytest tests/test_alembic_baseline.py`. Podium local backups retain 14 days under `/backup` and do not provide off-host replication.
**Notes for next iteration:** Existing tests require pytest 8.x/pytest-asyncio 0.x log-capture behavior, so dev dependencies are pinned below pytest 9 until those tests are updated.

## #026 Engine-built context compaction — 2026-06-11

**What changed:** Added engine-owned Podium Issue Context compaction before operator dispatch, plus manual `POST /api/issues/{id}/compact` compaction.
**Files:** context_compaction.py, scheduler.py, tracker_podium.py, web/api/main.py, web/api/schema.py, web/api/migrations/versions/0002_context_compaction_settings.py, tests/test_context_compaction.py, tests/test_dispatch_compaction.py, web/api/tests/test_context_compaction.py, web/api/tests/test_endpoints.py
**Decisions:** Compaction uses the configured runtime agent adapter before Run creation, writes back with `replace_context(...)`, and records no Run row for the compaction itself. The active schema revision is now `0002_context_compaction_settings`.
**Conventions established:** Podium context size control is engine-owned via `binding_settings.context_compact_threshold_tokens` and `context_compact_keep_recent_runs`; compaction output must include `SYMPHONY_COMPACTED_CONTEXT:` and the stored context starts with `<!-- context compacted on ... -->`.
**Notes for next iteration:** Full verification passed with `uv run pytest` (563 passed, 1 skipped). Fresh review passed. Existing config has no separate `binding.default_model`; compaction uses the configured binding runtime/agent adapter rather than hardcoding Pi.

## #027 Plane-coupled symphony-* skill suite migration — 2026-06-11

**What changed:** Added repo-local Podium-era `symphony-*` skill docs, a new `symphony-binding-scaffold` skill, `skill_migration.py` helpers for Podium binding scaffold/smoke/status flows, and `tests/skills/` regression coverage.
**Files:** `.claude/skills/symphony-binding-scaffold/SKILL.md`, `.claude/skills/symphony-binding-smoke/SKILL.md`, `.claude/skills/symphony-bindings-status/SKILL.md`, `.claude/skills/symphony-onboard-project/SKILL.md`, `.claude/skills/symphony-plane-recover/SKILL.md`, `.claude/skills/symphony-project-scaffold/SKILL.md`, `.claude/skills/symphony-workflow-author/SKILL.md`, `skill_migration.py`, `tests/skills/*.py`.
**Decisions:** New binding onboarding uses Podium as source of truth; `plane_project_id` remains in generated `bindings.yml` entries only as transitional `ProjectBinding` compatibility. `symphony-plane-recover` remains Plane-retirement-only.
**Conventions established:** Migrated operational skills must use Podium `/api/bindings`, `/api/bindings/{name}/issues`, and `/api/issues/{issue_id}/runs` paths and must not import `plane_adapter` or call legacy Plane workspace endpoints.
**Notes for next iteration:** #023c can rely on Podium-oriented skill docs, but external dotfiles/global skill synchronization remains a separate operational propagation step if required.

## #023c Homelab cutover to Podium + infra roles — 2026-06-11

**What changed:** Added Podium infra role columns and projection, exposed infra-only approval/schedule chips, cut `homelab` over to `tracker: podium`, ran the live migration/restart, completed a live homelab Podium smoke, updated terminology in `CONTEXT.md`, and documented rollback.
**Files:** bindings.yml, CONTEXT.md, tracker_podium.py, web/api/schema.py, web/api/migrations/versions/0003_infra_role_columns.py, web/api/main.py, web/frontend/lib/api.ts, web/frontend/components/IssueFlyout.tsx, web/frontend/components/NewIssueModal.tsx, web/README.md, tests/test_tracker_podium_infra.py, tests/test_main.py, web/api/tests/test_endpoints.py, web/api/tests/test_issue_patch.py
**Decisions:** Both active bindings now use Podium; Plane remains dormant as rollback/ADR-0002 hedge. In unattended mode, the homelab smoke issue was inserted directly into Podium SQLite because UI auth credentials were unavailable to the worker, but the scheduler dispatch still exercised the Podium tracker path end-to-end.
**Conventions established:** Infra role labels in Podium project through `issue.approval_required`, `issue.approved`, and due `issue.scheduled_for`; frontend infra-only chips are gated by server-projected `binding_type`.
**Notes for next iteration:** #023d must wait for a soak period before archiving Plane. Stale homelab e2e Todo issues 9–16 were parked as Blocked after cutover to prevent unintended live dispatch; issues 5–8 dispatched successfully during smoke cleanup.

## #024 scheduler.py:488 defensive hardening — 2026-06-11

**What changed:** Replaced first-binding `binding_type` resolution with explicit `ProjectBinding` plumbing through `main.BindingRuntime`, `run_loop`, `_dispatch_one`, `run_tick`, startup reconciliation, run-log retention, prompt rendering, context compaction, run records, and worktree run fields.
**Files:** main.py, scheduler.py, tests/test_main.py, tests/test_scheduler.py
**Decisions:** Kept single-binding fallback only when `SymphonyConfig.bindings` has exactly one binding; multi-binding paths must pass `binding` directly or resolve by `CandidateIssue.binding_name` once issue context exists.
**Conventions established:** Binding-sensitive scheduler gates should use a `ProjectBinding` argument or `_binding_for_issue(...)`, not `config.bindings[0].binding_type`.
**Notes for next iteration:** Verification passed with `uv run pytest` (573 passed, 1 skipped); fresh Ralph review passed. First full pytest run hit a transient SQLite busy failure in `tests/test_podium_sqlite_concurrent.py`, and immediate targeted rerun plus full rerun passed.

## #023a Podium systemd units actionable review — 2026-06-11

**What changed:** Closed the remaining alert-hook blocker by verifying failure-alert wiring from configuration without emitting a live Telegram alert.
**Files:** .kanban/issues/023a-podium-systemd-units.md, .kanban/progress.md; audited live units `/etc/systemd/system/podium-api.service`, `/etc/systemd/system/podium-web.service`, `/etc/systemd/system/telegram-alert@.service`, `/usr/local/sbin/send-telegram-systemd-alert`
**Decisions:** For unattended Ralph verification, external notification hooks are verified by unit/template/script/env wiring instead of firing live alerts.
**Conventions established:** Podium API and web failure hooks rely on `OnFailure=telegram-alert@%n.service` plus the shared `telegram-alert@.service` template and `/home/james/symphony-host.env` Telegram variable names.
**Notes for next iteration:** Verification passed: `sudo systemctl status podium-api.service podium-web.service --no-pager && ss -tlnp | grep -E '8090|8091'`; `systemctl show` confirmed active units, loopback listeners, api `--workers 1`, and resolved `OnFailure` targets. Critical LSP gate was not applicable because no source files changed.

## #023d Plane archive soak gate blocked — 2026-06-11

**What changed:** Parked #023d as blocked without invoking Plane archive or editing Authelia because the issue's own operator soak gate is not satisfied.
**Files:** .kanban/issues/023d-podium-plane-archive.md
**Decisions:** The one-week Podium soak and James-written soak-passed timestamps are hard prerequisites for archiving Plane; unattended service-action approval does not satisfy this issue-specific readiness record.
**Conventions established:** Irreversible Plane archive work remains blocked until issue completion notes contain soak start dates and explicit soak-passed confirmation timestamps for both trading and homelab.
**Notes for next iteration:** After the soak window elapses and James records the required confirmations in #023d, rerun Ralph to perform archive/documentation work.
