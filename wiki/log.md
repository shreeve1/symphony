# Wiki Log

Append entries with this format:

## [YYYY-MM-DD] type | Title

- Actor: agent or human
- Inputs: paths or prompt summary
- Outputs: changed pages
- Notes: key decisions or unresolved questions

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
