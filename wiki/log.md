# Wiki Log

Append entries with this format:

## [YYYY-MM-DD] type | Title

- Actor: agent or human
- Inputs: paths or prompt summary
- Outputs: changed pages
- Notes: key decisions or unresolved questions

---

## [2026-06-12] session-update | #038 Podium Inbox dismissal and resurface

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #038 implementation; commits `e7b0bd6`, `a0c3ebb`, `0344e78`; `.kanban/issues/038-podium-inbox-dismiss-resurface.md`; `.kanban/progress.md`; `web/api/main.py`; `tracker_podium.py`; `web/api/tests/test_inbox.py`; `tests/test_tracker_podium.py`; `web/frontend/components/Sidebar.tsx`; `web/frontend/lib/api.ts`; `web/frontend/tests/inbox.spec.ts`.
- Outputs: new `wiki/analyses/podium-038-inbox-dismiss-resurface.md`; updated `wiki/CLAIMS.md` (C-0137..C-0139); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured state-preserving Inbox dismissal, guarded dismiss endpoint, WebSocket publish, resurface clearing on transitions into `in_review`/`blocked`, optimistic Sidebar dismiss UX, and follow-up that #039 can remove the dashboard attention list. Verification passed: `PATH=/home/james/.local/bin:$PATH uv run pytest -q` (652 passed, 1 skipped), `pnpm exec tsc --noEmit`, `pnpm test:e2e` (37 passed), touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS_WITH_NOTES`. No secrets, no `.env` contents, no transcript.

## [2026-06-12] session-update | Podium password rotation helper

- Actor: agent (Pi)
- Inputs: operator request to make the successful Podium password-change workflow easier; `web/README.md`; `web/cli/podium.py`; `scripts/podium-change-password.sh`.
- Outputs: added `scripts/podium-change-password.sh`; updated `web/README.md`; updated `wiki/analyses/podium-018-auth.md`; updated `wiki/CLAIMS.md` (C-0132); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured the low-risk helper/runbook path: generate the bcrypt hash via the existing CLI, leave env editing and `podium-api.service` restart as explicit operator steps, and document `PODIUM_SESSION_SECRET` rotation only for force-logout. Verification passed: `bash -n scripts/podium-change-password.sh` and `git diff --check`. No secrets, no `.env` contents, no live service restart.

## [2026-06-12] session-update | Claude Code hook harness personalization (re-applied)

- Actor: agent (Claude, `personalize-harness` skill + wiki update)
- Inputs: current session; `pyproject.toml`, `uv.lock`, `.venv`, `CLAUDE.md`; generated `.claude/settings.json` + `.claude/hooks/{validate-syntax,block-bash-pattern,pre-git-checks,reinject-rules}.sh`; ruff/pytest baseline measurements; `~/.claude/skills/personalize-harness/SKILL.md` (global skill edit, outside repo).
- Outputs: `wiki/raw/sessions/2026-06-12-claude-code-harness.md`; `wiki/analyses/claude-code-harness-profile.md`; `wiki/CLAIMS.md` C-0130..C-0131; `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`; corrected `CLAUDE.md` "Quick Checks" (`python3 -m pytest` → `uv run pytest`).
- Notes: Team-layer Claude Code harness — 4 hooks (blocking syntax-validate afterWrite, blocking bash guard, blocking pre-git ruff-on-staged + `uv run pytest`, advisory compact reinject). Decisions: ruff at commit-time/changed-files-only (no `[tool.ruff]` config → repo-wide baseline red 38/82 + 5 lint); test gate is `uv run pytest` not bare `python3 -m pytest` (system python3 lacks alembic, .venv has it, 615 passed/1 skip/53s) — drove the `CLAUDE.md` quick-check correction; alembic stays project-only (declared dep, locked, in `.venv` 1.18.4), do not install system-wide. Path guard + Stop self-review skipped by operator choice. Live bug caught + fixed: rm guard matched safe `/tmp` deletes, re-anchored to root/home boundaries. Skill hardened with mandatory baseline-verification/runner-resolution step. **This update was first written then wiped by concurrent Ralph #033–#036 archive work (which reclaimed claim IDs C-0126/C-0127); re-applied here with claims renumbered to C-0130/C-0131.** Sibling of the Pi harness (C-0121/C-0122). No secrets, no env contents, no transcript.

## [2026-06-12] session-update | repo-local Symphony operational skills

- Actor: agent (Pi)
- Inputs: operator request to reconcile Symphony skills into `/home/james/symphony/.claude/`; dotfiles copies of `symphony-restart` and `symphony-troubleshooter`; repo-local `.claude/skills/symphony-*`; `tests/skills/`.
- Outputs: added `.claude/skills/symphony-restart/SKILL.md`; added `.claude/skills/symphony-troubleshooter/SKILL.md`; added `tests/skills/test_restart_troubleshooter.py`; updated `wiki/analyses/symphony-skills-index.md`; updated `wiki/CLAIMS.md` (C-0129); updated `wiki/log.md`.
- Notes: Project-local consolidation kept existing Podium-era skills canonical, did not overwrite them with stale dotfiles copies, and did not copy non-Symphony `debug-hermes`. Follow-up dotfiles commit `06fa9a6` removed the stale global `symphony-*` copies so project-local skills no longer collide. Verification covered skill tests and stale Plane scaffold strings; no secrets or `.env` contents read.

## [2026-06-12] session-update | #035 archived engine-terminal contract

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #035 implementation; commits `c8118c1`, `32c16d3`, `65cd128`; `.kanban/issues/035-podium-archive-engine-terminal-contract.md`; `.kanban/progress.md`; `tracker_podium.py`; `web/api/main.py`; `scheduler.py`; `tests/test_tracker_podium.py`; `web/api/tests/test_worktree_api.py`; `tests/test_trading_podium_dispatch.py`.
- Outputs: updated `wiki/analyses/podium-issue-archive-design.md`; updated `wiki/CLAIMS.md` (C-0123/C-0124 superseded, C-0126..C-0127 added); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured #035 landing the archived terminal engine contract: guarded `transition_state`, idle archive PATCH worktree teardown, active-run deferral, explicit scheduler `archived_terminal` skip after run-row finalization, and #036 purge still pending. Verification passed: `PATH="$PWD/.venv/bin:$HOME/.local/bin:$PATH" python3 -m pytest -q` (622 passed, 1 skipped), touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | #023c Podium homelab cutover + infra role projection

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #023c implementation; commits `037d78e`, `89ae1af`, `811e5e8`; `bindings.yml`; `tracker_podium.py`; `web/api/schema.py`; `web/api/migrations/versions/0003_infra_role_columns.py`; `web/api/main.py`; `web/frontend/components/IssueFlyout.tsx`; `web/frontend/components/NewIssueModal.tsx`; `web/README.md`; `CONTEXT.md`; `tests/test_tracker_podium_infra.py`; `tests/test_main.py`; `.kanban/issues/023c-podium-homelab-cutover.md`; `.kanban/progress.md`.
- Outputs: new `wiki/analyses/podium-023c-homelab-cutover.md`; updated `wiki/concepts/podium-tracker.md`; updated `wiki/analyses/adr-0005-replace-plane-with-podium.md`; updated `wiki/CLAIMS.md` (C-0104..C-0106, C-0080 superseded, C-0083 note); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured homelab now live on Podium, both active bindings on Podium, infra role columns/projection, infra-only UI chips, live migration/restart/smoke evidence, rollback docs, and stale e2e issue parking. Verification passed: `uv run pytest` (586 passed, 1 skipped), `pnpm exec tsc --noEmit`, live `alembic upgrade head`, `symphony-host.service` restart, touched-file LSP diagnostics with no critical errors, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no raw transcript.

## [2026-06-11] session-update | #023a Podium systemd units actionable review

- Actor: agent (Pi, Ralph actionable review)
- Inputs: issue #023a actionable review; commit `9a9b30d`; `.kanban/issues/023a-podium-systemd-units.md`; `.kanban/progress.md`; live unit snapshots `/etc/systemd/system/podium-api.service`, `/etc/systemd/system/podium-web.service`, `/etc/systemd/system/telegram-alert@.service`, `/usr/local/sbin/send-telegram-systemd-alert`.
- Outputs: new `wiki/raw/podium-api.service`; `wiki/raw/podium-web.service`; `wiki/raw/telegram-alert@.service`; `wiki/raw/send-telegram-systemd-alert`; new `wiki/sources/podium-systemd-units.md`; updated `wiki/analyses/adr-0005-replace-plane-with-podium.md`; `wiki/CLAIMS.md` (C-0103 and C-0065 note); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured landed Podium sibling units, API `--workers 1`, web loopback `HOST=127.0.0.1`, `OnFailure=telegram-alert@%n.service` wiring, and the unattended verification rule to check external-notification wiring without firing live Telegram alerts. Verification passed: `sudo systemctl status podium-api.service podium-web.service --no-pager && ss -tlnp | grep -E '8090|8091'`; env variable presence checked without printing secrets.

## [2026-06-11] session-update | #027 Podium skill-suite migration

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #027 implementation; commits `07b0c36`, `628ea08`, `73ce14c`; `.claude/skills/symphony-binding-scaffold/SKILL.md`; `.claude/skills/symphony-binding-smoke/SKILL.md`; `.claude/skills/symphony-bindings-status/SKILL.md`; `.claude/skills/symphony-onboard-project/SKILL.md`; `.claude/skills/symphony-plane-recover/SKILL.md`; `.claude/skills/symphony-project-scaffold/SKILL.md`; `.claude/skills/symphony-workflow-author/SKILL.md`; `skill_migration.py`; `tests/skills/`; `.kanban/issues/027-podium-skill-suite-migration.md`; `.kanban/progress.md`.
- Outputs: updated `wiki/analyses/symphony-skills-index.md`; `wiki/CLAIMS.md` (C-0099..C-0102, C-0049 Podium supersession note); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured Podium-era `symphony-*` skill paths, new `symphony-binding-scaffold`, smoke/status Podium endpoint migration, Plane-only scaffold/recover split, tracker-agnostic workflow-author posture, and test coverage. Verification passed: `uv run pytest` (572 passed, 1 skipped), touched-file LSP diagnostics clean, fresh review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | #026 Podium Issue Context compaction

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #026 implementation; commits `db4a559`, `c24cd5b`; `context_compaction.py`; `scheduler.py`; `tracker_podium.py`; `web/api/main.py`; `web/api/schema.py`; `web/api/migrations/versions/0002_context_compaction_settings.py`; `tests/test_context_compaction.py`; `tests/test_dispatch_compaction.py`; `web/api/tests/test_context_compaction.py`; `.kanban/issues/026-podium-engine-context-compaction.md`; `.kanban/progress.md`.
- Outputs: `wiki/analyses/podium-026-context-compaction.md`; `wiki/CLAIMS.md` (C-0095..C-0098, C-0068 supersession note); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured engine-owned context compaction, `binding_settings` threshold/keep settings, pre-Run configured-agent invocation, `replace_context(...)`, no-Run-row invariant, manual compact endpoint, and ADR-0005 zero-schema-impact correction. Verification passed: `uv run pytest` (563 passed, 1 skipped), touched-file LSP diagnostics clean, fresh review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | #023b Podium Alembic baseline + SQLite backup wiring

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #023b implementation; commits `5df8784`, `e633be7`, `849898f`; `tests/test_alembic_baseline.py`; `web/api/migrations/env.py`; `web/api/migrations/README.md`; `scripts/podium-backup.sh`; `/etc/cron.d/podium-backup`; `web/README.md`; `.kanban/issues/023b-podium-alembic-and-backup.md`; `.kanban/progress.md`.
- Outputs: `wiki/raw/sessions/2026-06-11-podium-023b-alembic-backup.md`; `wiki/raw/podium-backup.cron`; `wiki/analyses/podium-023b-alembic-backup.md`; `wiki/CLAIMS.md` (C-0092..C-0094); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured Alembic/runtime schema parity testing, logger-preserving Alembic config, migration rule docs, cron-based SQLite `.backup` with 14-day retention, restore-drill evidence, and pytest 8.x dev-tooling pin. Verification passed: `uv run pytest` (554 passed, 1 skipped) plus backup file check. No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | #022 Podium restart Run reconciliation + run-log retention

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #022 implementation; commits `3bd8957`, `0667480`, `9686183`; `scheduler.py`; `tracker_podium.py`; `tests/test_run_reconcile.py`; `tests/test_log_retention.py`; `.kanban/issues/022-podium-restart-reconcile-and-log-retention.md`; `.kanban/progress.md`.
- Outputs: `wiki/analyses/podium-022-run-reconcile-log-retention.md`; `wiki/CLAIMS.md` (C-0089..C-0091); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured landed startup Run reaping, parent-Issue blocked transition, preserved worktrees, run-log retention semantics (90 days or newest 100 per Issue), startup + 24h scheduler wiring, and structured `run_reconcile_*` / `log_retention_*` pairs. Verification passed: `uv run pytest` (552 passed, 1 skipped). No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | #021 Podium worktree opt-in + FF-only auto-merge

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #021 implementation; commits `74b024d`, `b59f193`, `f0c5d37`; `web/api/worktree.py`; `agent_runner.py`; `plane_adapter.py`; `tracker_podium.py`; `web/api/main.py`; `tests/test_agent_runner.py`; `web/api/tests/test_worktree.py`; `web/api/tests/test_worktree_api.py`; `web/frontend/tests/worktree.spec.ts`; `.kanban/issues/021-podium-worktree-auto-merge.md`; session wiki query of `wiki/index.md` and `wiki/ROUTING.md` before implementation.
- Outputs: `wiki/analyses/podium-021-worktree-auto-merge.md`; `wiki/CLAIMS.md` (C-0084..C-0088); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured deterministic Podium worktree path/branch, dispatch cwd switching, FF-only Done merge and teardown, blocked abort comments, archive toggle behavior, frontend chip lifecycle, and dotenv masking fix for the auth missing-secret test. Verification passed: `uv run pytest` (545 passed, 1 skipped) and `pnpm test:e2e` (15 passed). No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | #021 dev-review fixes

- Actor: agent (Pi after dev-review-claude)
- Inputs: dev-review findings for commits `5858e7c..97f9ae6`; `web/api/main.py`; `scheduler.py`; `agent_runner.py`; `web/api/worktree.py`; `tests/test_trading_podium_dispatch.py`; `web/api/tests/test_worktree.py`; `web/api/tests/test_worktree_api.py`; `web/frontend/lib/api.ts`; `web/frontend/components/IssueFlyout.tsx`; `.kanban/issues/021-podium-worktree-auto-merge.md`; `.kanban/progress.md`.
- Outputs: updated `wiki/analyses/podium-021-worktree-auto-merge.md`; updated `wiki/CLAIMS.md` (C-0086..C-0088); updated `wiki/log.md`.
- Notes: Captured final blocked-row WebSocket publish after merge aborts, async `to_thread` git work, Run-row worktree metadata, server-derived Issue worktree path/branch fields, combined done+worktree-off PATCH precedence, and review-fix verification: `uv run pytest` (547 passed, 1 skipped), `pnpm exec tsc --noEmit`, and `pnpm test:e2e` (15 passed). No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | #020 trading→Podium cutover smoke + run-log finalization bug

- Actor: agent (Claude, cutover smoke + wiki update)
- Inputs: session performing the #020 operator smoke; commits `12289da`, `8eb4aa6`, `eb1a706`; `tracker_podium.py`; `scheduler.py:438-478`; `web/api/db.py:8-22`; `main.py:75-81`; `tests/test_trading_podium_dispatch.py`; live `podium.db` (issue 17 / run 6) and `journalctl` traceback.
- Outputs: new `wiki/raw/sessions/2026-06-11-podium-020-cutover-smoke.md`; promoted `wiki/analyses/analysis-session-020-cutover-smoke.md`; `wiki/CLAIMS.md` (added C-0082, C-0083; refinement notes on C-0062, C-0067); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured the production-only run-log crash (`adapter.db_path=None` → unwritable `/var/lib/symphony/runs` → `PermissionError` in `_write_run_log`), the `__post_init__` fix, the run-log co-location convention, the masked-test lesson, and the trading-live-on-Podium milestone. Refines (does not supersede) C-0062/C-0067. Follow-up: consider making `RUN_LOG_ROOT` follow `resolve_db_path` fallback (#024). No secrets, no `.env` contents, no transcript.

---

## [2026-06-09] setup | Initial wiki scaffold

- Actor: agent (Claude Code, llm-wiki-setup skill)
- Inputs: James interview answers — domain: Symphony scheduler internals + runbook; sources: CLAUDE.md, CONTEXT.md, ~/homelab/docs/runbooks/automation/symphony.md, docs/, Plans/, with expanded coverage; commit wiki to git; auto-promote candidates (no James gate); inline citation style.
- Outputs: created wiki/ tree (raw/, raw/sessions/, candidates/, sources/, entities/, concepts/, analyses/, assets/); created wiki/README.md, wiki/index.md, wiki/log.md, wiki/ROUTING.md, wiki/CLAIMS.md; queued CLAUDE.md refactor and first ingest.
- Notes: Raw-source git policy not explicitly confirmed for binaries — .gitignore left untouched; will warn before committing large binaries. Auto-promotion overrides default candidate gate.

## [2026-06-09] ingest | all-three-tiers (Tier 1 + 2 + 3)

- Actor: agent (Claude Code, llm-wiki-setup skill, Ingest workflow, batch at James' request "all three")
- Inputs:
  - **Tier 1**: copied to `wiki/raw/`: `workflow-homelab.md` (from `~/homelab/WORKFLOW.md`), `workflow-trading.md` (from `~/trading/crypto-trading-agents/WORKFLOW.md`), `symphony-host.service` (from `/etc/systemd/system/`), `brainstorm-pi-swap.md` (from `artifacts/brainstorming/`), 4 spec PRDs (from `artifacts/specs/*/PRD.md`).
  - **Tier 2**: read in-tree for behavioural extraction: `schedule.py`, `blocked_reconciler.py`, `scheduler.py`, `agent_runner.py`, `run_worktree.py`, `prompt_renderer.py` (no raw copy — code on disk is the canonical source).
  - **Tier 3**: read 8 `symphony-*` SKILL.md frontmatter+intros from `~/.claude/skills/`; counted tests in `tests/*.py`.
- Outputs:
  - **Tier 1**: `sources/symphony-host-service-unit.md`; `entities/workflow-homelab.md`, `entities/workflow-trading.md`; `analyses/brainstorm-pi-swap.md`, `analyses/pi-swap-review-specs.md`.
  - **Tier 2**: `concepts/schedule-comment-grammar.md`, `concepts/blocked-reconciler-implementation.md`, `concepts/scheduler-loop.md`, `concepts/agent-runner-and-worktree.md`, `concepts/prompt-renderer.md`.
  - **Tier 3**: `analyses/symphony-skills-index.md`, `analyses/symphony-tests-index.md`.
  - Claims: C-0026..C-0049 added to `wiki/CLAIMS.md`.
  - Index Sources/Entities/Concepts/Analyses expanded across all four buckets.
  - ROUTING.md expanded: Architecture, Operations, Bindings & Repos, Scheduling, Plan/Build/Approve, Blocked Reconciler, Executor/Agent, Decisions, Plan History, Skills & Tooling all updated; new **Tests** branch added.
- Notes:
  - Tier 2 module pages document behaviour contracts that aren't derivable from CONTEXT.md or the ADRs — constants, regexes, naming schemes, sort precedence, fail-fast guardrails. They are deliberately not full code transcripts; code on disk remains canonical.
  - Discovered divergence (C-0045): `prompt_renderer.py` defaults `IssueData.mode = "conversation"` and emits a Conversation Mode block — but CONTEXT.md's Mode entry lists only plan/build/execute. Either CONTEXT.md needs a Conversation Mode entry or the renderer's conversation block is a deliberately-undocumented runtime extension. Flag for grill-me.
  - scheduler.py (2633 LOC) is intentionally summarised, not transcribed. `concepts/scheduler-loop.md` lists constants, semaphore/cooldown model, and the top-level async surface; deeper sections (sanitisation, dirty-base approval protocol, mode-resolution algorithm) should be ingested as separate concept pages when questions surface.
  - 4 spec PRDs in `artifacts/specs/` consolidated into one `pi-swap-review-specs.md` rather than 4 separate pages — they share a single target and reviewer format.
  - 8 `symphony-*` SKILL.md files documented as an index page rather than per-skill pages — SKILL.md is the source of truth and lives in a separate dotfiles repo.
  - 14 test files documented as a coverage map; test bodies not transcribed.
  - Auto-promoted all new pages.

## [2026-06-09] ingest | batch — runbook, ADRs, plans, bindings, tracker_contract

- Actor: agent (Claude Code, llm-wiki-setup skill, Ingest workflow, batch mode at James' request "batch all")
- Inputs: copied to `wiki/raw/`: `runbook-symphony.md` (from `~/homelab/docs/runbooks/automation/symphony.md`), `adr-0001-claude-tmux.md` through `adr-0004-tracker-contract.md` (from `docs/adr/`), `plan-refactor-move-symphony-to-home.md` through `plan-ticket-scheduling.md` (5 plans from `plans/`), `bindings.yml`, `tracker_contract.py`.
- Outputs:
  - sources/: `runbook-symphony.md`
  - concepts/: `symphony-operations.md`, `tracker-contract.md`
  - analyses/: `adr-0001-claude-tmux.md`, `adr-0002-generalize-symphony.md`, `adr-0003-worktree-per-run.md`, `adr-0004-tracker-contract.md`, `symphony-plan-history.md`
  - entities/: `binding-homelab.md`, `binding-trading.md`
  - claims: C-0011..C-0025 added to `wiki/CLAIMS.md`
  - index Sources/Entities/Concepts/Analyses populated
  - ROUTING.md expanded with Scheduling, Plan/Build/Approve, Blocked Reconciler, Telegram, Executor/Agent, Plan History branches
- Notes:
  - Plan landed-status verified against `git log`: `refactor-move-symphony-to-home` (98c6359), `symphony-pi-executor-swap` (8af5dab), `symphony-ticket-scheduling` (36352f9); `symphony-plan-approve-workflow` landed pre-ADR-0004 (homelab-router-era); `symphony-operational-improvements` partial — flagged for verification (`plane comments`, stderr surfacing).
  - C-0010 note refined: `approval.enabled: false` in bindings.yml is the **engine gate** flag; the label-driven plan/approve flow (mode:plan → approval-required → mode:build) is a separate mechanism. CONTEXT.md says homelab opts in — that wording refers to the label flow, not the engine flag.
  - Deferred per-entity breakouts for Mode/Agent/Workflow/Done Marker/Verdict/Run/Run Worktree/Landing/Project Scaffold/Tracker Adapter/Agent Adapter — `concepts/symphony-engine.md` covers each in dedicated section. Create on demand when routing pressure justifies it.
  - Auto-promoted all new pages.

## [2026-06-09] ingest | CONTEXT.md (Symphony glossary)

- Actor: agent (Claude Code, llm-wiki-setup skill, Ingest workflow)
- Inputs: `CONTEXT.md` (copied to `wiki/raw/symphony-context.md`)
- Outputs: `wiki/sources/symphony-context.md` (source summary, promoted), `wiki/concepts/symphony-engine.md` (engine concept, promoted), C-0001..C-0010 added to `wiki/CLAIMS.md`, index Sources/Concepts updated, ROUTING.md Project Overview + Architecture branches populated.
- Notes: Source touches multiple potential entity pages (Project Binding, Mode, Agent, Workflow, Tracker Adapter, Tracker Contract, Agent Adapter, Done Marker, Verdict, Run, Run Worktree, Landing, Project Scaffold). Held off on a fan-out into 13 entity pages — single overview concept page captures the engine model. Recommend per-entity pages on demand or as part of next ingest pass. Auto-promoted both new pages (no James gate).

## [2026-06-09] session-update | trading smoke rate-limit debugging

- Actor: agent (Pi, wiki-update skill, SessionUpdate workflow)
- Inputs: current debugging session; `scheduler.py`; `tests/test_scheduler.py`; `prompt_renderer.py`; `wiki/raw/workflow-trading.md`; journal evidence for trading smoke issues `6fbfd86a-36b2-4548-9b41-2a80fb66506c` and `0ab7f64c-3ad4-468d-8c2e-4d408c35f076`; commits `a269e32`, `fbff782`, `c4944be`.
- Outputs: `wiki/raw/sessions/2026-06-09-trading-smoke-rate-limit.md`; `wiki/analyses/trading-smoke-rate-limit-debugging.md`; updates to `wiki/concepts/scheduler-loop.md`, `wiki/concepts/prompt-renderer.md`, `wiki/entities/workflow-trading.md`, `wiki/CLAIMS.md` (C-0050..C-0053), `wiki/index.md`, `wiki/ROUTING.md`, and `wiki/log.md`.
- Notes: Captured root causes and fixes for post-agent Plane 429 recovery, shared Plane cooldown, optional-label scan pressure, and the remaining dirty-worktree proof blocker: unlabeled issues render as conversation mode and should not edit files. No secrets, `.env` contents, or full transcript stored.

## [2026-06-09] session-update | thin engine E2E test + service restart

- Actor: agent (Pi, wiki-update skill, SessionUpdate workflow)
- Inputs: current session; `agent_runner.py`; `scheduler.py`; `config.py`; `main.py`; journalctl evidence for smoke issue `b0b79316`; commit `e73e924`; `symphony-host.service` unit config.
- Outputs: `wiki/raw/sessions/2026-06-09-thin-engine-e2e-test.md`; `wiki/candidates/analysis-thin-engine-e2e-test.md`; `wiki/candidates/concept-thin-engine-v2.md`; CLAIMS.md updates (C-0007, C-0009, C-0016, C-0018, C-0019, C-0020, C-0040, C-0041, C-0042, C-0044 — supersession/historical notes); `wiki/index.md` (2 candidate rows); `wiki/ROUTING.md` (Thin Engine + Service Restart branches); `wiki/log.md` (this entry).
- Notes: Thin engine E2E smoke test verified full dispatch lifecycle. Root cause for worktree behavior was code drift (service never restarted after thin engine commit). Service restarted successfully. Stale worktree cleaned. Promoted concept page `agent-runner-and-worktree.md` substantially stale — new candidate supersedes it. 10 claims annotated with thin-engine context. No secrets stored.

## [2026-06-10] session-update | Podium #014 new-issue flow + review + modal evolution

- Actor: agent (Claude Code, wiki-update skill, SessionUpdate workflow)
- Inputs: current session; commits `a68cccf`, `f0de67b`, `4aab377`, `a6157f3`, `bf7cfd0`; `web/api/main.py`; `web/api/seed.py`; `web/api/tests/test_issue_create.py`; `web/frontend/components/NewIssueModal.tsx`; `web/README.md`; `.kanban/issues/014/015/020`.
- Outputs: `wiki/raw/sessions/2026-06-10-podium-014-new-issue-flow.md`; `wiki/analyses/podium-014-new-issue-flow.md` (auto-promoted after lint); `wiki/CLAIMS.md` (C-0054..C-0058); `wiki/index.md` (analyses row + removed two stale candidate-queue rows for already-promoted thin-engine pages); `wiki/ROUTING.md` (Podium Web UI branch); `wiki/log.md` (this entry).
- Notes: Captured #014 endpoint contract, INSERT OR IGNORE seeding pivot and its #015 resurrection constraint, /options dropdown endpoint design (static agents mirror scheduler validation; KNOWN_MODELS placeholder; live git branches), close-on-success modal UX deviation accepted by James, flyout chip removals, and free-text agent/model constraint for #020. Index candidate-queue cleanup was low-risk maintenance (files no longer exist; promoted versions indexed). No secrets, no transcript.

## [2026-06-10] ingest | ADR-0005 (replace Plane with Podium) + Podium tracker concept page

- Actor: agent (Claude Code, Ingest workflow; AI-consumption optimized at James's request)
- Inputs: `docs/adr/0005-replace-plane-with-podium.md` (copied to `wiki/raw/adr-0005-replace-plane-with-podium.md`); live code grounding `web/api/schema.py`, `web/api/db.py`, `web/api/main.py`, `web/api/seed.py`, `web/api/migrations/versions/0001_initial.py`; `scheduler.py:488`. Reviewed done slices #012a–#013 against existing wiki coverage; two gaps found (ADR-0005 never ingested; Podium impl had no concept page).
- Outputs: `wiki/raw/adr-0005-replace-plane-with-podium.md` (raw copy); `wiki/analyses/adr-0005-replace-plane-with-podium.md` (decision page, auto-promoted); `wiki/concepts/podium-tracker.md` (impl concept page, auto-promoted); `wiki/CLAIMS.md` (C-0059..C-0068 added; C-0004 supersession note for Podium); `wiki/index.md` (concepts + analyses rows); `wiki/ROUTING.md` (Podium Web UI + Decisions branches expanded); `wiki/log.md` (this entry).
- Notes: Pages written dense/fact-first for future AI sessions, not human narrative. Verified live: `scheduler.py:488` is_coding-off-bindings[0] bug (C-0066); two distinct enums issue.state vs run.state (C-0067); db-path chain + check_same_thread rationale (web/api/db.py). ADR-0005 reconciliation captured: ADR-0002 "stay on Plane" superseded; ADR-0001/0003 already inert via thin engine v2, worktree posture reversed to opt-in. podium-api/web systemd units not yet created at ingest time (C-0065 reflects design). `.kanban/` gitignored — claims cite code paths + commits primarily. No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | Podium #017 WebSocket live updates

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #017 implementation; commit `0a50bc7`; `web/api/main.py`; `web/api/seed.py`; `web/api/tests/test_websocket.py`; `web/frontend/components/QueryProvider.tsx`; `web/frontend/components/NewIssueModal.tsx`; `web/frontend/tests/live-sync.spec.ts`; `web/frontend/playwright.config.ts`.
- Outputs: `wiki/analyses/podium-017-live-updates.md`; `wiki/CLAIMS.md` (C-0069..C-0072); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured WS `/api/ws` in-process fanout, issue/run event contract, frontend TanStack Query live cache strategy, reconnect/disconnect pill behavior, optimistic-create race fix, `websockets` runtime dependency, and last-write-wins concurrency decision. No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | Podium #018 shared-password auth

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #018 implementation; commit `b8a50f0`; `web/api/auth.py`; `web/api/main.py`; `web/api/tests/test_auth.py`; `web/cli/podium.py`; `web/frontend/components/AppShell.tsx`; `web/frontend/app/login/page.tsx`; `web/frontend/tests/auth.spec.ts`.
- Outputs: `wiki/analyses/podium-018-auth.md`; `wiki/CLAIMS.md` (C-0073..C-0076); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured bcrypt shared-password auth, required env contract, signed `podium_session` cookie, HTTP and WebSocket auth gates, frontend login/logout redirect contract, set-password stdout-only helper, and test-auth convention. No production secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | Podium #025 prompt renderer Podium path

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #025 implementation; commit `36a7cd4`; `prompt_renderer.py`; `skill_mode_map.py`; `tests/test_prompt_renderer_podium.py`.
- Outputs: updated `wiki/concepts/prompt-renderer.md`; `wiki/CLAIMS.md` (C-0077..C-0078); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured `tracker_kind="podium"`, direct `comments_md`/`context_md` rendering, non-truncating Podium comments, `skill_mode_map.SKILL_TO_MODE`, and the transitional Skill→Mode bridge. No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | Podium #019 tracker adapter

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #019 implementation; commits `9e84869`, `37c5170`, `1eff632`; `config.py`; `main.py`; `scheduler.py`; `tracker_adapter.py`; `tracker_podium.py`; `web/api/db.py`; `tests/test_tracker_podium.py`; `tests/test_podium_sqlite_concurrent.py`; `tests/test_engine_against_podium.py`.
- Outputs: updated `wiki/concepts/podium-tracker.md`; `wiki/CLAIMS.md` (C-0079..C-0081); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured `tracker: plane|podium` binding validation, runtime tracker protocol, SQLite Podium adapter, WAL/busy-timeout concurrency posture, no direct `plane_adapter` import in `tracker_podium.py`, and scheduler `stores_context` path for Podium `context_md`. No secrets, no `.env` contents, no transcript.

## [2026-06-11] session-update | Podium #023d trading Plane archive + reverse-proxy docs

- Actor: agent (Claude, interactive session + wiki update)
- Inputs: issue #023d execution (descoped to trading-only); `symphony-plane-recover archive` run; `bindings.yml`; `CONTEXT.md`; `web/README.md`; `config.py:345,391`; `tests/test_trading_podium_dispatch.py`; `.kanban/issues/023d-podium-plane-archive.md`.
- Outputs: `wiki/raw/sessions/2026-06-11-podium-023d-trading-plane-archive.md`; `wiki/analyses/podium-023d-trading-plane-archive.md`; `wiki/CLAIMS.md` (C-0107, C-0108; supersession notes on C-0023→superseded, C-0059, C-0104); updated `wiki/entities/binding-trading.md` (retire banner, historical Tracker Contract section); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured the operator-waived soak gate, the irreversible trading Plane archive (HTTP 204, `archived_at: 2026-06-11T22:42:15Z`), the live `tracker_contract` removal → `DEFAULT_CONTRACT` fallback, the README Authelia reverse-proxy snippet, and the deferred homelab archive. No secrets, no `.env` contents (PLANE_API_KEY only echoed as char-count during env sourcing), no transcript.
- Unresolved: homelab Plane archive follow-up issue (e.g. 023e) not yet created; Authelia/proxy live edit + Podium reachability confirmation operator-pending; no git commit yet.
- Addendum: added a non-destructive drift banner to `wiki/raw/bindings.yml` (immutable snapshot) flagging it predates #023c/#023d; body preserved verbatim, still valid YAML. Raw immutability honored — flag, never silently rewrite.

## [2026-06-12] session-update | #023d reverse-proxy bring-up (podium-web LAN bind)

- Actor: agent (Claude, interactive session + wiki update)
- Inputs: operator-chosen FQDN `podium.testytech.net` + proxy upstream `10.20.20.16:8091`; `podium-web.service` unit edit (`HOST=127.0.0.1`→`HOST=10.20.20.16`, backup `.bak.2026-06-12`, daemon-reload + restart); reachability verification (`10.20.20.16:8091`→200, loopback→000); `symphony-host.service` restart onto sha `82462e6`; `web/frontend/package.json` start script.
- Outputs: updated `web/README.md` (FQDN + LAN upstream + bind requirement, commit `82462e6`); `wiki/CLAIMS.md` (added C-0109; annotated C-0065, C-0103; C-0109 marked applied/verified); `wiki/sources/podium-systemd-units.md`; `wiki/raw/podium-web.service` (drift banner, immutable body); `wiki/analyses/podium-023d-trading-plane-archive.md` (bring-up section); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Frontend `start` is `next start -H ${HOST:-0.0.0.0}`, so the unit `HOST` env selects the bind interface; loopback-only was why the LAN proxy 404'd. LAN bind exposes the unauthenticated port 8091 — Authelia stays the gate, firewall optional. No secrets, no `.env` contents, no transcript.
- Unresolved: end-to-end `https://podium.testytech.net` via Authelia not yet confirmed (last #023d acceptance box); homelab archive follow-up issue (023e) not created; commits `a24d229`/`82462e6` unpushed.

## [2026-06-12] session-update | Podium frontend deploy hazard + atomic deploy script + UI cosmetics

- Actor: agent (Claude, interactive session + wiki update)
- Inputs: cosmetic frontend request (collapsible sidebar, card quick-view); live MIME/400 console errors after in-place `next build`; root-cause + recovery via `podium-web.service` restart; `web/frontend/deploy.sh` (new); `web/frontend/next.config.mjs` (`distDir` env override); `web/frontend/components/AppShell.tsx`; `web/frontend/components/IssueCard.tsx`; `web/frontend/.gitignore`; `systemctl cat podium-web.service`; `web/frontend/package.json`.
- Outputs: `wiki/raw/sessions/2026-06-12-podium-frontend-deploy-and-ui-cosmetics.md`; `wiki/analyses/podium-frontend-deploy-cosmetics.md` (promoted); `wiki/CLAIMS.md` (C-0110 deploy hazard + atomic deploy, C-0111 UI cosmetics); `wiki/index.md`; `wiki/ROUTING.md` (Operations, Podium Web UI, Service Restart & Deployment routes); `wiki/log.md`.
- Notes: Root cause — `next start` serves prebuilt `.next` with no hot reload; `next build` overwrites `.next` in place, so the live server served old HTML against new chunk hashes (400/`text/html` MIME, app stuck at "Checking session…"). Fix is atomic staging-swap `deploy.sh` (build to `.next.staging`, stop→swap→start). Build-only validated; stop/swap/start untested on a real deploy. No secrets, no `.env` contents, no transcript.
- Unresolved: five frontend changes uncommitted (latest commit `eef75d1`); first real `deploy.sh` run will exercise the live swap path; card shows pinned `preferred_agent`/`preferred_model`, not last Run's actual agent/model (would need a new issue-list field).

## [2026-06-12] grill-me + decision | Podium UX/observability tuning plan + ADR-0006

- Actor: agent (Claude, /grill-me session) + James (operator decisions)
- Inputs: `.kanban/archive/2026-06-11/progress.md`; wiki (`index.md`, `ROUTING.md`, `analyses/podium-017-live-updates.md`, `analyses/podium-frontend-deploy-cosmetics.md`, `CLAIMS.md`); code reads `web/api/main.py`, `web/frontend/components/{NewIssueModal,RunDetailPanel,Sidebar}.tsx`, `web/frontend/app/page.tsx`, `config.py`, `agent_runner.py`, `scheduler.py`, `tracker_podium.py`.
- Decisions (plan, not yet implemented): (1) searchable zero-dep comboboxes replacing native FieldSelect; model dropdown auto-populates from a new git-tracked `models.yml` (agent-tagged), filtered by selected agent; maintained by two manually-run skills `symphony-skills` (wraps `podium skills refresh`) + `symphony-models` (edits models.yml). (2) Run liveness = frontend elapsed timer + refresh-on-exit, no live log tail. (3) Live bridge = gated TanStack `refetchInterval` (~3s while queued/running, slow/off idle), WS kept for optimistic operator-action UI. (4) Board overview at `/` (replaces placeholder): per-binding + global state counts, cross-binding attention list, per-binding last activity — all client-side from existing payload; failure-trend chart deferred (needs new run-history endpoint).
- Outputs: `docs/adr/0006-engine-state-surfaced-by-polling-not-websocket.md` (new ADR, accepted); `wiki/raw/adr-0006-engine-state-polling.md` (immutable copy); `wiki/analyses/adr-0006-engine-state-polling.md` (promoted); `wiki/CLAIMS.md` (C-0112 engine writes bypass in-process WS hub → gated polling; C-0113 run log written once at `communicate()` exit; annotated C-0070 as closed/unachievable-as-written); `wiki/index.md`; `wiki/ROUTING.md` (Decisions route); `wiki/log.md`.
- Verified facts: `grep -c "run.updated" scheduler.py tracker_podium.py` = 0/0; only publish is API-startup seed at `main.py:126`. `agent_runner.py:272` `process.communicate(timeout=...)` blocks until exit (no incremental log). Landing `/` is a placeholder; no aggregate view exists.
- Notes: No secrets, no `.env` contents, no transcript. Plan implementation (models.yml, skills, frontend comboboxes/timer/overview, polling) is future work — only the live-bridge architecture decision was promoted to an ADR.
- Unresolved: none of the four plan items implemented yet; ADR-0006 + claims uncommitted (local working tree).

## [2026-06-12] session-update | #028 models.yml catalog + searchable dropdowns

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #028 implementation; commits `99bd541`, `1773db9`, `8bda239`; `models.yml`; `web/api/main.py`; `web/api/tests/test_issue_create.py`; `web/frontend/lib/api.ts`; `web/frontend/components/NewIssueModal.tsx`; `web/frontend/tests/new-issue.spec.ts`; `.kanban/progress.md`.
- Outputs: `wiki/analyses/podium-028-model-catalog-searchable-dropdowns.md`; updated `wiki/analyses/adr-0006-engine-state-polling.md`; updated `wiki/CLAIMS.md` (C-0114, C-0115; C-0056 superseded); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured model catalog source-of-truth move from `KNOWN_MODELS` to `models.yml`, shared `_validate_models()` contract, `/options` model-object shape, graceful invalid-catalog fallback, agent-filtered searchable comboboxes, free-text Agent/Model preservation, and #032 validator reuse note. Verification passed: `uv run pytest` (591 passed, 1 skipped), `pnpm exec tsc --noEmit`, `pnpm test:e2e` (16 passed), touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS_WITH_NOTES` due an unrelated live-sync flake in the reviewer run. No secrets, no `.env` contents, no transcript.

## [2026-06-12] session-update | #031 board overview dashboard

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #031 implementation; commits `e95a394`, `c93500a`, `8387e6a`; `web/frontend/app/page.tsx`; `web/frontend/app/[binding]/page.tsx`; `web/frontend/components/KanbanBoard.tsx`; `web/frontend/tests/dashboard.spec.ts`; `.kanban/issues/031-podium-board-overview-dashboard.md`; `.kanban/progress.md`.
- Outputs: `wiki/analyses/podium-031-board-overview-dashboard.md`; updated `wiki/CLAIMS.md` (C-0116); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured root `/` cross-binding dashboard, client-side aggregation from existing issue-list payloads, global and per-binding `issue.state` roll-ups, last-activity timestamps, blocked/failed attention rows, and `/<binding>?issue=<id>` flyout deep-link behavior. Verification passed: `uv run pytest` (591 passed, 1 skipped), `pnpm exec tsc --noEmit`, `pnpm test:e2e` (21 passed), touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-12] session-update | #032 catalog maintenance skills

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #032 implementation; commits `e1744bc`, `6325bc1`, `4e83e1a`; `.claude/skills/symphony-skills/SKILL.md`; `.claude/skills/symphony-models/SKILL.md`; `tests/skills/test_catalog_maintenance_skills.py`; `.kanban/issues/032-symphony-skills-and-models-maintenance-skills.md`; `.kanban/progress.md`.
- Outputs: updated `wiki/analyses/symphony-skills-index.md`; updated `wiki/CLAIMS.md` (C-0117); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured manual Skill-table refresh flow, direct `models.yml` list/add/remove maintenance, shared `_load_models()` / `_validate_models()` lint gate, no bespoke model helper, and safety rules forbidding service restarts, Plane calls, env-file reads, direct DB model edits, and secret printing. Verification passed: `uv run pytest tests/skills/` (15 passed), touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-12] session-update | operator-reply comments

- Actor: agent (Claude, `/dev-build` of `plans/feature-operator-reply-comments.md` + wiki update)
- Inputs: implementation across `web/api/main.py` (`ReplyCreate`, `ALLOWED_REPLY_STATES`/`ACTIVE_RUN_STATES`, `reply_to_issue` endpoint + `ctx`-strip 422 fix), `prompt_renderer.py` (`flag_operator_replies`), `web/frontend/lib/api.ts` (`postReply`), `web/frontend/components/IssueFlyout.tsx` (`ReplyComposer`); new tests `web/api/tests/test_reply.py`, `tests/test_prompt_renderer_podium.py` additions, `web/frontend/tests/reply.spec.ts`; fixtures lifted into `web/api/tests/conftest.py`.
- Outputs: new raw capture `wiki/raw/sessions/2026-06-12-operator-reply-comments.md`; new promoted concept `wiki/concepts/operator-reply.md`; cited edit to `wiki/concepts/prompt-renderer.md` (`render_previous_comments_block` directive flag, updated 2026-06-12); `wiki/CLAIMS.md` C-0118, C-0119; updated `wiki/index.md`, `wiki/ROUTING.md`, `wiki/log.md`.
- Notes: Durable new fact — posting an operator reply carries a `todo` state-flip side effect that re-dispatches the agent (single atomic conditional `UPDATE` with `COALESCE(comments_md,'')`, state + `latest_run_state` guard; 409/422/400/404 contract). Continuity is transcript re-feed (`comments_md` + `context_md`), not pi session resume. Closes the bidirectional Issue Comments gap (C-0068); extends Podium render_prompt (C-0077). Verification: `pytest web/api/tests` 72 passed/1 skipped, `pytest tests/ --ignore=alembic` 471 passed (one flaky concurrency test passes in isolation; fails only under concurrent CPU/SQLite load), `playwright reply.spec.ts` 3 passed, `tsc --noEmit` clean, sample Podium prompt eyeballed showing directive + reply. No secrets, no `.env` contents, no transcript. Pre-existing unrelated `tests/test_alembic_baseline.py` collection error (`alembic` not installed) ignored.

## [2026-06-12] session-update | frontend e2e clobbers live .next (crash-loop + deploy.sh recovery)

- Actor: agent (Claude, post-restart frontend incident)
- Inputs: live diagnosis of "Checking session…" hang after `podium-web.service` restart — `.next` had no `BUILD_ID` (dev build written at 05:04 by `playwright test` during the operator-reply `/dev-build`); `next start` crash-looped (NRestarts=13); referenced chunks 400ing with `text/html`. Evidence: `journalctl -u podium-web.service`, `web/frontend/playwright.config.ts:39-44`, `web/frontend/package.json`, `web/frontend/deploy.sh`, port/listener + curl probes.
- Outputs: updated `wiki/analyses/podium-frontend-deploy-cosmetics.md` (new "Second trigger: Playwright e2e clobbers the live `.next`" section, deploy.sh first-real-run validation, isolation follow-up, frontmatter sources); `wiki/CLAIMS.md` C-0120; updated `wiki/ROUTING.md`, `wiki/log.md`.
- Notes: Durable fact — `pnpm test:e2e` runs `next dev` into the shared `web/frontend/.next` with no `NEXT_DIST_DIR`, silently overwriting the production build `podium-web` serves; damage is masked until the next restart, then crash-loops on a missing `BUILD_ID`. Recovery is `deploy.sh` (staging-swap rebuild), not a bare restart — also confirmed deploy.sh's stop/swap/start path end-to-end for the first time (chunks 200 with correct MIME, tree clean, root 200). Prevention follow-up: isolate e2e webServer via throwaway `NEXT_DIST_DIR` or keep `test:e2e` out of live-dir automated builds. No code change this pass; no secrets, no `.env` contents, no transcript.

## [2026-06-12] session-update | Pi personal harness profile

- Actor: agent (Pi, personalize-harness-pi + wiki update)
- Inputs: current session; `.rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md`; `.pi/extensions/personal-harness.ts`; `CLAUDE.md`; `web/README.md`; `web/frontend/playwright.config.ts`; `wiki/analyses/podium-frontend-deploy-cosmetics.md`; `wiki/analyses/symphony-tests-index.md`.
- Outputs: `wiki/raw/sessions/2026-06-12-personal-harness-pi.md`; `wiki/analyses/personal-harness-pi-profile.md`; `wiki/CLAIMS.md` (C-0121..C-0122); `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Captured the generated project-local Pi harness, advisory/deferred project-check posture, manual-only Playwright posture, reference-only guidance decision, selected safety blockers, and verification results. No secrets, no `.env` contents, no `/home/james/symphony-host.env` contents, no full transcript.

## [2026-06-12] session-update | Issue archive ("delete button") design grilling

- Actor: agent (Claude, grill-me design session + wiki update)
- Inputs: current conversation (grill-me on delete-vs-done); codebase facts from `web/api/schema.py`, `web/api/main.py`, `web/api/db.py`, `web/api/worktree.py`, `tracker_podium.py`, `web/frontend/lib/issues.ts`, `web/frontend/components/KanbanBoard.tsx`, `web/frontend/components/IssueFlyout.tsx`; `CONTEXT.md` (Tracker Contract entry edited twice this session).
- Outputs: `wiki/raw/sessions/2026-06-12-issue-archive-state-design.md`; `wiki/analyses/podium-issue-archive-design.md` (auto-promoted after lint); `wiki/CLAIMS.md` C-0123..C-0125; `wiki/index.md`; `wiki/ROUTING.md`; `wiki/log.md`.
- Notes: Design accepted, not implemented — sixth `archived` state (no new column), engine-terminal contract (no verdict transition post-run, deferred worktree teardown via `remove_worktree`), mid-run archive allowed, per-column board minimize with localStorage persistence, Archive button in flyout, 14-day opportunistic purge on `updated_at` with FK-safe delete order. Hazards recorded: `transition_state` resurrection bug, worktree-vs-issue "archive" terminology collision. C-0021/C-0064 (five states) left active — supersession deferred to the implementation pass. ADR offered, declined. No secrets, no env contents, no transcript.

<<<<<<< Updated upstream
## [2026-06-12] session-update | #034 archived issue state core

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #034 implementation; commits `11a1ff3`, `efc8c67`, `0b90159`, `a97e186`, `0569271`; `.kanban/issues/034-podium-archived-state-core.md`; `.kanban/progress.md`; `web/api/main.py`; `web/api/schema.py`; `web/api/migrations/versions/0004_archived_state.py`; `web/api/tests/test_issue_patch.py`; `web/api/tests/test_reply.py`; `web/frontend/lib/issues.ts`; `web/frontend/components/KanbanBoard.tsx`; `web/frontend/components/IssueFlyout.tsx`; `web/frontend/tests/archive.spec.ts`; `web/frontend/tests/board.spec.ts`.
- Outputs: updated `wiki/analyses/podium-issue-archive-design.md`; updated `wiki/CLAIMS.md` (C-0067, C-0123..C-0125); updated `wiki/index.md`; updated `wiki/log.md`.
- Notes: Captured #034 landing the sixth `archived` Issue state through migration/runtime schema, PATCH and list filtering, reply 409 guard coverage, rightmost default-collapsed Archived board column, and no-confirm flyout Archive action. Engine-terminal teardown (#035) and 14-day purge (#036) remain pending. Verification passed: `PATH="$PWD/.venv/bin:$HOME/.local/bin:$PATH" python3 -m pytest -q` (618 passed, 1 skipped), `pnpm exec tsc --noEmit`, `PATH="$HOME/.local/bin:$PATH" pnpm test:e2e` (32 passed), touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS_WITH_NOTES` with only minor notes addressed by follow-up commits. No secrets, no `.env` contents, no transcript.

## [2026-06-12] session-update | #036 archived retention purge

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #036 implementation; commits `b589cef`, `cb079c4`, `6cf44b9`; `.kanban/issues/036-podium-archived-retention-purge.md`; `.kanban/progress.md`; `web/api/main.py`; `web/api/tests/test_archive_purge.py`.
- Outputs: updated `wiki/analyses/podium-issue-archive-design.md`; updated `wiki/CLAIMS.md` (C-0127 superseded, C-0128 added); updated `wiki/index.md`; updated `wiki/log.md`.
- Notes: Captured #036 landing the archived retention purge: API startup + post-archive PATCH sweeps, hardcoded 14-day `updated_at` window, FK-safe per-issue delete order, best-effort run-log unlink, rollback behavior, and filesystem-based defensive worktree cleanup even when `worktree_active` is stale. Verification passed: `PATH="$PWD/.venv/bin:$HOME/.local/bin:$PATH" python3 -m pytest -q` (633 passed, 1 skipped), touched-file LSP diagnostics clean, `git diff --check` clean, secret scan clean, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.

## [2026-06-12] session-update | First live Podium skill catalog refresh

- Actor: agent (Claude Code, symphony-skills + wiki-update)
- Inputs: live `python -m web.cli.podium skills refresh` run (dry-run → FK failure → repoint → success); `web/cli/podium_skills.py`; `web/cli/podium.py`; `web/api/seed.py`; `.claude/skills/symphony-skills/SKILL.md`; in-session DB inspections of `podium.db`.
- Outputs: new `wiki/raw/sessions/2026-06-12-podium-skills-catalog-refresh.md`; new `wiki/analyses/podium-skills-catalog-refresh.md` (candidate created, linted, auto-promoted); `wiki/CLAIMS.md` C-0133..C-0136 added, C-0055 marked superseded (by C-0136); `wiki/index.md` and `wiki/ROUTING.md` updated.
- Notes: Captured three durable refresh-CLI behaviors: dry-run prints catalog TSV not a diff (SKILL.md step 2 wrong — follow-up to fix wording); single-source scan contract (default `~/.claude/skills` dotfiles symlink; repo-local `symphony-*` skills not cataloged; two `--source` runs clobber); `issue.preferred_skill` FK blocks stale-row delete with clean whole-run rollback, and manual-row protection is deletion-only (manual `diagnose` row converted to file-backed by upsert). James approved live refresh and repointing 12 e2e issues from `/diagnose` to `diagnose`. Result: 50-row catalog, zero pending diff, catalog maintenance skill tests 6 passed. Skill seeding confirmed retired in `web/api/seed.py` → C-0055 superseded. No secrets, no env contents, no transcript.

## [2026-06-12] session-update | catalog-alpha/bravo fixture leak cleanup

- Actor: agent (Claude Code)
- Inputs: James report of phantom dropdown entries; `podium.db` skill rows; `web/frontend/tests/skill-catalog.spec.ts`; `web/frontend/tests/fixtures.ts`; git history (`6d9f1c6`).
- Outputs: deleted `catalog-alpha`/`catalog-bravo` rows from live `podium.db` (48 rows remain, zero manual rows); updated `wiki/analyses/podium-skills-catalog-refresh.md` resulting-state section; updated C-0136 note in `wiki/CLAIMS.md`.
- Notes: Rows were leaked Playwright e2e fixtures — an older `seedSkills` wrote `source=''` into the live DB, which refresh's manual-row protection then preserved. Current `fixtures.ts` isolates via `PODIUM_DB_PATH` → `web/test-results/podium-e2e.db` and tags `source='e2e'` (self-healing: refresh deletes leaked `'e2e'` rows). No FK or code references existed at deletion. No secrets, no env contents.
=======
## [2026-06-12] session-update | Pi personal harness hardening pass

- Actor: agent (Pi follow-up)
- Inputs: `.pi/extensions/personal-harness.ts`; `.rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md`; `wiki/raw/sessions/2026-06-12-personal-harness-pi.md`; post-generation setup review findings.
- Outputs: tracked `wiki/raw/personal-harness-pi-profile.md`; updated `.pi/extensions/personal-harness.ts`; updated `.rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md`; updated `wiki/analyses/personal-harness-pi-profile.md`; updated `wiki/CLAIMS.md`; updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Hardened bash secret-read blocking for `/home/james/symphony-host.env` and `.env`-like files, switched runtime roots to `PROFILE.targetRepo`, moved the durable profile reference into tracked wiki raw storage, changed automatic pytest beforeGit into a manual `uv run pytest -q` reminder, and replaced source-only dry checks with mocked-event verification coverage. No secrets or `.env` contents captured.
>>>>>>> Stashed changes

## [2026-06-12] session-update | #039 dashboard attention list removal

- Actor: agent (Pi, Ralph + wiki update)
- Inputs: issue #039 implementation; commits `1ca6fe2`, `5d6918f`, `c91bdcc`; `.kanban/issues/039-podium-remove-dashboard-attention-list.md`; `.kanban/progress.md`; `web/frontend/app/page.tsx`; `web/frontend/tests/dashboard.spec.ts`.
- Outputs: updated `wiki/analyses/podium-031-board-overview-dashboard.md`; updated `wiki/CLAIMS.md` (C-0116 note, C-0140 added); updated `wiki/index.md`; updated `wiki/ROUTING.md`; updated `wiki/log.md`.
- Notes: Captured #039 removal of the Dashboard Needs attention list after Sidebar Inbox became canonical. Verification passed: `PATH=/home/james/.local/bin:$PATH pnpm test:e2e` (37 passed), `pnpm exec tsc --noEmit`, touched-file LSP diagnostics clean, and fresh Ralph review `RALPH_REVIEW: PASS`. No secrets, no `.env` contents, no transcript.
