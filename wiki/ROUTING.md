# Wiki Routing

Use this file after reading `index.md` when narrowing a wiki-backed question to likely branches.

## Project Overview

- Pages: `concepts/symphony-engine.md`, `sources/symphony-context.md`
- Keywords: symphony, scheduler, host-native, plane, polling, bindings, dispatch

## Architecture

- Pages: `concepts/symphony-engine.md`, `concepts/tracker-contract.md`, `concepts/scheduler-loop.md`, `concepts/agent-runner-and-worktree.md`, `concepts/prompt-renderer.md`, `analyses/trading-smoke-rate-limit-debugging.md`, `analyses/adr-0002-generalize-symphony.md`, `analyses/adr-0003-worktree-per-run.md`, `analyses/adr-0004-tracker-contract.md`
- Keywords: binding lifecycle, dispatch loop, reconcile, prompt_renderer, plane_adapter, plane_poller, scheduler, agent_runner, run_worktree, tracker_contract, code_version, notifier, Run, Run Worktree, Verdict, Done Marker, Mode, Agent Adapter, Tracker Adapter, Tracker Contract, Landing, concurrency cap, semaphore, in-memory reconcile, git-ref handoff, run_id, deterministic naming, post-agent 429, pending_review_issue_ids, shared Plane cooldown, optional label scan

## Operations

- Pages: `concepts/symphony-operations.md`, `sources/runbook-symphony.md`, `sources/symphony-host-service-unit.md`, `analyses/symphony-skills-index.md`, `analyses/trading-smoke-rate-limit-debugging.md`
- Keywords: systemd, symphony-host.service, restart ritual, env file, lock file, journalctl, telegram-alert, symphony-host.env, status check, smoke evidence, common failure pointers, 401, 404, 429, worktree_dirty, healthcheck remediation, EnvironmentFile, OPENCODE_BIN drift, RuntimeDirectory, Plane rate limit, retained worktree, dirty-worktree smoke

## Bindings & Repos

- Pages: `entities/binding-homelab.md`, `entities/binding-trading.md`, `entities/workflow-homelab.md`, `entities/workflow-trading.md`, `concepts/tracker-contract.md`, `analyses/adr-0004-tracker-contract.md`
- Keywords: bindings.yml, homelab, trading, crypto-trading-agents, WORKFLOW.md, smoke ticket, project scaffold, Role, TrackerRole, RoleBinding, PlaneUserMapping, default_agent, base_branch, approval.enabled, landing.mode, project_id, project_slug, workspace_slug, plane_uuid, medium-risk autonomy, Trading Safety Boundary, excluded services

## Plane Integration

- Pages: `concepts/symphony-engine.md`, `concepts/tracker-contract.md`, `entities/binding-homelab.md`, `entities/binding-trading.md`
- Keywords: PLANE_API_URL, PLANE_API_KEY, workspace slug, project id, todo, in review, running, blocked, done, labels, X-API-Key, label UUIDs, state UUIDs

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

- Pages: `analyses/adr-0001-claude-tmux.md`, `analyses/symphony-plan-history.md`, `analyses/brainstorm-pi-swap.md`, `concepts/symphony-engine.md`, `concepts/agent-runner-and-worktree.md`
- Keywords: pi, pi-coding-agent, --print, --no-session, --provider, --model, glm-5.1, zai, claude, tmux, send-keys, load-buffer, paste-buffer, capture-pane, Done Marker, SYMPHONY_RESULT, SYMPHONY_SUMMARY, dev-review-claude, CLIPROXY_API_KEY, OpenCode (retired), verify_pi_support, silent-failure guardrail, PiAgentAdapter, ClaudeAgentAdapter, RoutingAgentAdapter, ZAI_API_KEY

## Decisions

- Pages: `analyses/adr-0001-claude-tmux.md`, `analyses/adr-0002-generalize-symphony.md`, `analyses/adr-0003-worktree-per-run.md`, `analyses/adr-0004-tracker-contract.md`, `analyses/brainstorm-pi-swap.md`, `analyses/pi-swap-review-specs.md`, `sources/symphony-context.md`
- Keywords: ADR, CONTEXT.md, design rationale, tradeoffs, deprecation, sortie, build vs buy, adapter seam, role indirection, brainstorm, locked decisions, rejected designs, audit loop

## Plan History

- Pages: `analyses/symphony-plan-history.md`, `analyses/brainstorm-pi-swap.md`, `analyses/pi-swap-review-specs.md`
- Keywords: refactor-move-symphony-to-home, symphony-operational-improvements, symphony-pi-executor-swap, symphony-plan-approve-workflow, symphony-ticket-scheduling, landed status, dev-review-claude, Codex review, brainstorm artifact, review-PRD, round-3, END_OF_FINDINGS

## Skills & Tooling

- Pages: `analyses/symphony-skills-index.md`
- Keywords: symphony-project-scaffold, symphony-workflow-author, symphony-restart, symphony-bindings-status, symphony-binding-smoke, symphony-plane-recover, symphony-onboard-project, symphony-troubleshooter, typed-slug confirmation, dry-run preview, umbrella skill

## Tests

- Pages: `analyses/symphony-tests-index.md`
- Keywords: pytest, test_scheduler, test_schedule, test_plane_cli, FakeTransport, validation contract, 435 tests, coverage map, py_compile
