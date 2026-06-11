# Wiki Log

Append entries with this format:

## [YYYY-MM-DD] type | Title

- Actor: agent or human
- Inputs: paths or prompt summary
- Outputs: changed pages
- Notes: key decisions or unresolved questions

---

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
