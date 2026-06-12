# Wiki Routing

Use this file after reading `index.md` when narrowing a wiki-backed question to likely branches.

## Project Overview

- Pages: `concepts/symphony-engine.md`, `sources/symphony-context.md`
- Keywords: symphony, scheduler, host-native, plane, polling, bindings, dispatch

## Architecture

- Pages: `concepts/symphony-engine.md`, `concepts/tracker-contract.md`, `concepts/scheduler-loop.md`, `concepts/agent-runner-and-worktree.md`, `concepts/prompt-renderer.md`, `analyses/trading-smoke-rate-limit-debugging.md`, `analyses/adr-0002-generalize-symphony.md`, `analyses/adr-0003-worktree-per-run.md`, `analyses/adr-0004-tracker-contract.md`, `analyses/analysis-session-020-cutover-smoke.md`, `analyses/podium-021-worktree-auto-merge.md`, `analyses/podium-022-run-reconcile-log-retention.md`, `analyses/podium-023b-alembic-backup.md`, `analyses/podium-023c-homelab-cutover.md`, `analyses/podium-026-context-compaction.md`
- Keywords: binding lifecycle, dispatch loop, reconcile, prompt_renderer, skill_mode_map, tracker_kind, comments_md, context_md, preferred_skill, skill-to-mode, plane_adapter, plane_poller, scheduler, agent_runner, run_worktree, tracker_contract, code_version, notifier, Run, Run Worktree, Verdict, Done Marker, Mode, Agent Adapter, Tracker Adapter, Tracker Contract, Landing, concurrency cap, semaphore, in-memory reconcile, git-ref handoff, run_id, deterministic naming, post-agent 429, pending_review_issue_ids, shared Plane cooldown, optional label scan, run log path, RUN_LOG_ROOT, _write_run_log, _finish_run_record, _start_run_record, adapter db_path, run-log co-location, /var/lib/symphony/runs, PermissionError run finalization, trading cutover, #020 smoke, stale-running reconciler finalization, worktree_active, podium worktree, worktrees/<binding>/<issue_id>, podium/<binding>/<issue_id>, FF-only merge, dirty base precheck, restart-orphan, run_reconcile_begin, run_reconcile_done, log_retention_begin, log_retention_done, LOG_RETENTION_INTERVAL, prune_run_logs

## Operations

- Pages: `concepts/symphony-operations.md`, `sources/runbook-symphony.md`, `sources/symphony-host-service-unit.md`, `sources/podium-systemd-units.md`, `analyses/symphony-skills-index.md`, `analyses/trading-smoke-rate-limit-debugging.md`, `analyses/podium-023b-alembic-backup.md`, `analyses/podium-frontend-deploy-cosmetics.md`
- Keywords: systemd, symphony-host.service, podium-api.service, podium-web.service, restart ritual, env file, lock file, journalctl, telegram-alert, telegram-alert@.service, send-telegram-systemd-alert, OnFailure, wiring-only alert verification, symphony-host.env, status check, smoke evidence, common failure pointers, 401, 404, 429, worktree_dirty, healthcheck remediation, EnvironmentFile, OPENCODE_BIN drift, RuntimeDirectory, Plane rate limit, retained worktree, dirty-worktree smoke, podium backup, /backup/podium, /etc/cron.d/podium-backup, sqlite .backup, restore drill, HOST bind address, HOST=10.20.20.16, podium.testytech.net, 10.20.20.16:8091, reverse proxy upstream, Authelia gate, LAN bind, next start -H, frontend not reachable, frontend deploy, deploy.sh, next build, in-place rebuild, .next overwrite, stale chunk, MIME text/html, 400 css, Checking session hang, atomic staging swap, NEXT_DIST_DIR, .next.staging, .next.prev, distDir, tsconfig rewrite noise, hard refresh

## Bindings & Repos

- Pages: `entities/binding-homelab.md`, `entities/binding-trading.md`, `entities/workflow-homelab.md`, `entities/workflow-trading.md`, `concepts/tracker-contract.md`, `analyses/adr-0004-tracker-contract.md`, `analyses/podium-023d-trading-plane-archive.md`
- Keywords: bindings.yml, homelab, trading, crypto-trading-agents, WORKFLOW.md, smoke ticket, project scaffold, Role, TrackerRole, RoleBinding, PlaneUserMapping, default_agent, base_branch, approval.enabled, landing.mode, project_id, project_slug, workspace_slug, plane_uuid, medium-risk autonomy, Trading Safety Boundary, excluded services, tracker_contract removed, DEFAULT_CONTRACT fallback, trading archived

## Plane Integration

- Pages: `concepts/symphony-engine.md`, `concepts/tracker-contract.md`, `entities/binding-homelab.md`, `entities/binding-trading.md`, `analyses/podium-023d-trading-plane-archive.md`
- Keywords: PLANE_API_URL, PLANE_API_KEY, workspace slug, project id, todo, in review, running, blocked, done, labels, X-API-Key, label UUIDs, state UUIDs, plane archive, projects/<id>/archive, archived_at, symphony-plane-recover archive, soak gate waived, 023d, Plane retirement, trading project archived, homelab archive deferred

## Scheduling

- Pages: `concepts/symphony-operations.md`, `concepts/schedule-comment-grammar.md`, `analyses/symphony-plan-history.md`
- Keywords: scheduled label, Symphony-Schedule, Symphony-Schedule-Cancelled, not_before, not_after, 12am-6am, America/Los_Angeles, maintenance window, plane schedule, plane unschedule, label-only schedule, one-shot, recurring, temporal, ScheduleEvent, ScheduleParseError, sort precedence, HTML normalisation, quote-aware

## Plan / Build / Approve

- Pages: `analyses/symphony-plan-history.md`, `concepts/symphony-engine.md`, `concepts/prompt-renderer.md`, `entities/workflow-homelab.md`, `entities/workflow-trading.md`, `analyses/trading-smoke-rate-limit-debugging.md`, `analyses/adr-0003-worktree-per-run.md`
- Keywords: mode:plan, mode:build, execute, approval-required, approved, plan handoff, git-ref handoff, _PLAN_HANDOFF_MARKER, plans/<slug>.md, Plans/<identifier>.md, dirty-worktree, plan_path_from_comments, Plan-Path trailer, Symphony completed plan., conversation mode, unlabeled ticket, file edits forbidden

## Blocked Reconciler

- Pages: `concepts/symphony-operations.md`, `concepts/blocked-reconciler-implementation.md`, `sources/runbook-symphony.md`
- Keywords: SYMPHONY_BLOCKED_RECONCILER_ENABLED, SYMPHONY_BLOCKED_RECONCILER_APPLY, SYMPHONY_BLOCKED_RECONCILER_INTERVAL_MS, blocked_reconcile_would_apply, blocked_reconcile_applied, blocked_reconcile_skipped, Patrol pass for, consecutive_passes, page_limit_reached, ReconcileRule, ReconcileDecision, BLOCKED_PAGE_SIZE

## Telegram

- Pages: `concepts/symphony-operations.md`, `sources/runbook-symphony.md`
- Keywords: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_HOME_CHANNEL, TelegramNotifier, send_sync, telegram_notifications_enabled, IN_REVIEW transition, BLOCKED transition, plane review, plane blocked, PLANE_FRONTEND_URL, PLANE_DASHBOARD_URL

## Executor / Agent

- Pages: `analyses/adr-0001-claude-tmux.md`, `analyses/symphony-plan-history.md`, `analyses/brainstorm-pi-swap.md`, `concepts/symphony-engine.md`, `concepts/agent-runner-and-worktree.md`, `concepts/thin-engine-v2.md`, `analyses/thin-engine-e2e-test.md`
- Keywords: pi, pi-coding-agent, --print, --no-session, --provider, --model, glm-5.1, zai, openai-codex, gpt-5.5, claude, tmux, send-keys, Done Marker, SYMPHONY_RESULT, SYMPHONY_SUMMARY, verify_pi_support, silent-failure guardrail, PiAgentAdapter, RoutingAgentAdapter, ZAI_API_KEY, thin-engine, coding-binding, no-worktree

## Thin Engine

- Pages: `concepts/thin-engine-v2.md`, `analyses/thin-engine-e2e-test.md`, `concepts/scheduler-loop.md`, `wiki/raw/sessions/2026-06-09-thin-engine-e2e-test.md`
- Keywords: thin engine, v2, e73e924, coding binding, is_coding, worktree removed, claude paused, pi only, run_worktree deleted, smoke test, code drift, provider drift, agent runs in repo

## Service Restart & Deployment

- Pages: `analyses/thin-engine-e2e-test.md`, `sources/symphony-host-service-unit.md`, `concepts/symphony-operations.md`, `analyses/podium-frontend-deploy-cosmetics.md`
- Keywords: restart ritual, code_sha, pre-sanity, git log HEAD drift, systemctl restart, service verification, stale worktree, git worktree remove, podium-web deploy, frontend rebuild, next build then restart, atomic staging swap, deploy.sh, .next.staging, .next.prev rollback, distDir override

## Decisions

- Pages: `analyses/adr-0001-claude-tmux.md`, `analyses/adr-0002-generalize-symphony.md`, `analyses/adr-0003-worktree-per-run.md`, `analyses/adr-0004-tracker-contract.md`, `analyses/adr-0005-replace-plane-with-podium.md`, `analyses/brainstorm-pi-swap.md`, `analyses/pi-swap-review-specs.md`, `sources/symphony-context.md`
- Keywords: ADR, CONTEXT.md, design rationale, tradeoffs, deprecation, sortie, build vs buy, adapter seam, role indirection, brainstorm, locked decisions, rejected designs, audit loop, retire Plane, Podium decision, Binding-is-Project, Skill subsumes Mode, Run first-class, worktree opt-in posture, tracker plane podium, ADR-0002 superseded, ADR-0001 ADR-0003 inert, ADR-0006, gated polling, refetchInterval, scheduler separate process, WebSocket gap, in-process hub, engine state not pushed, communicate blocks log, no live tail, elapsed timer, board overview, models.yml, symphony-models, symphony-skills, searchable dropdown, agent-filtered models

## Plan History

- Pages: `analyses/symphony-plan-history.md`, `analyses/brainstorm-pi-swap.md`, `analyses/pi-swap-review-specs.md`
- Keywords: refactor-move-symphony-to-home, symphony-operational-improvements, symphony-pi-executor-swap, symphony-plan-approve-workflow, symphony-ticket-scheduling, landed status, dev-review-claude, Codex review, brainstorm artifact, review-PRD, round-3, END_OF_FINDINGS

## Skills & Tooling

- Pages: `analyses/symphony-skills-index.md`, `analyses/personal-harness-pi-profile.md`
- Keywords: symphony-binding-scaffold, symphony-project-scaffold, symphony-workflow-author, symphony-restart, symphony-bindings-status, symphony-binding-smoke, symphony-plane-recover, symphony-onboard-project, symphony-troubleshooter, symphony-skills, symphony-models, skill_migration.py, Podium skill migration, Podium catalog maintenance, tracker: podium, POST /api/bindings/{name}/issues, GET /api/bindings, GET /api/issues/{issue_id}/runs, GET /api/skills, python -m web.cli.podium skills refresh, models.yml, _load_models, _validate_models, Plane retirement tool, typed-slug confirmation, dry-run preview, umbrella skill, personal-harness-pi, Pi personal harness, .pi/extensions/personal-harness.ts, Harness Profile, afterWrite syntax, beforeGit project checks, safety blockers

## Podium Web UI

- Pages: `concepts/podium-tracker.md`, `concepts/operator-reply.md`, `analyses/podium-issue-archive-design.md`, `analyses/adr-0005-replace-plane-with-podium.md`, `analyses/podium-014-new-issue-flow.md`, `analyses/podium-017-live-updates.md`, `analyses/podium-018-auth.md`, `analyses/podium-021-worktree-auto-merge.md`, `analyses/podium-022-run-reconcile-log-retention.md`, `analyses/podium-023b-alembic-backup.md`, `analyses/podium-023c-homelab-cutover.md`, `analyses/podium-023d-trading-plane-archive.md`, `analyses/podium-026-context-compaction.md`, `analyses/podium-028-model-catalog-searchable-dropdowns.md`, `analyses/podium-031-board-overview-dashboard.md`, `analyses/podium-frontend-deploy-cosmetics.md`, `wiki/raw/sessions/2026-06-10-podium-014-new-issue-flow.md`, `wiki/raw/sessions/2026-06-09-ui-brainstorm-handoff.md`, `wiki/raw/sessions/2026-06-12-operator-reply-comments.md`
- Keywords: podium, web ui, kanban board, board overview dashboard, root dashboard, global roll-up, binding summary cards, attention list, issue deep link, initialIssueId, ?issue=, new issue, POST issues, IssueCreate, IssuePatch, options endpoint, KNOWN_AGENTS, KNOWN_MODELS, models.yml, MODELS_PATH, _load_models, _validate_models, ModelOption, FieldCombobox, searchable dropdown, agent-filtered models, free-text model, branches dropdown, optimistic update, temp card, NewIssueModal, IssueFlyout, metadata chips, infra chips, approval_required, approved, scheduled_for, skill seeding, INSERT OR IGNORE, /diagnose, websocket, WS /api/ws, WebSocketHub, issue.updated, issue.created, run.updated, TanStack Query live cache, reconnect backoff, Disconnected retrying pill, live-sync.spec.ts, websocket fanout, last-write-wins, podium.db, PODIUM_DB_PATH, resolve_db_path, uvicorn 8090, --workers 1, next start 8091, next dev 8091, playwright e2e, persistent dev DB, FieldSelect, base_branch fallback, issue.state, run.state, queued running succeeded failed, todo in_review blocked done, check_same_thread, no-op guard, monotonic updated_at, 400 422 split, extra_forbidden, startup reaper, restart-orphan, Run table, latest_run_id, Binding-is-Project, Skill subsumes Mode, Skill→Mode bridge, skill_mode_map, preferred_skill, tracker_kind, tracker plane podium, tracker_podium, tracker_adapter, PodiumTrackerAdapter, stores_context, WAL, busy_timeout, podium-api.service, podium-web.service, podium systemd, PODIUM_PASSWORD_HASH, PODIUM_SESSION_SECRET, podium_session, bcrypt, auth, login, logout, whoami, set-password, API auth gate, WebSocket auth gate, Authelia 9091, comments_md, context_md, engine-built compaction, context_compaction, binding_settings, context_compact_threshold_tokens, context_compact_keep_recent_runs, SYMPHONY_COMPACTED_CONTEXT, replace_context, compact endpoint, Alembic, schema.py, ADR-0005, worktree_active, worktree chip, worktree.spec.ts, FF-only auto-merge, Worktree archived, run-log retention, log_path NULL, 90-day log pruning, newest 100 logs per issue, collapsible sidebar, PanelLeft toggle, podium:sidebar-open, sidebar collapse, IssueCard, agent pill, preferred_agent pill, preferred_model, priority badge removed, verdict pill removed, card quick-view, default agent, frontend deploy.sh, atomic staging swap, NEXT_DIST_DIR, .next.staging, in-place rebuild hazard, MIME 400, Checking session hang, operator reply, ReplyComposer, reply endpoint, POST reply, /api/issues/{id}/reply, Operator Reply block, reply-input, reply-send, reply-disabled-hint, reply-error, todo state-flip, reply re-dispatch, done reopen, flag_operator_replies, operator-reply directive, transcript re-feed, COALESCE comments_md, ALLOWED_REPLY_STATES, ACTIVE_RUN_STATES, ReplyCreate, postReply, isActiveRunState, next dev clobbers .next, e2e clobbers production build, Could not find a production build, BUILD_ID missing, podium-web crash-loop, NRestarts auto-restart, playwright webServer next dev, NEXT_DIST_DIR e2e isolation, deploy.sh staging swap recovery, test:e2e hazard, archived state, issue archive, delete button, archive button, sixth state, column minimize, collapse column, archived column, retention purge, 14-day purge, resurrection guard, engine-terminal, archived_terminal, deferred worktree teardown, mid-run archive, podium.collapsed localStorage

## Tests

- Pages: `analyses/symphony-tests-index.md`
- Keywords: pytest, test_scheduler, test_schedule, test_plane_cli, FakeTransport, validation contract, 435 tests, coverage map, py_compile, pytest 8, pytest-asyncio 0, test_alembic_baseline, alembic baseline
