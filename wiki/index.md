# Wiki Index

## Sources

| Page | Summary | Sources | Updated |
|------|---------|---------|---------|
| [sources/symphony-context.md](sources/symphony-context.md) | Summary of `CONTEXT.md` — Symphony's canonical domain glossary | `wiki/raw/symphony-context.md`, `CONTEXT.md` | 2026-06-09 |
| [sources/runbook-symphony.md](sources/runbook-symphony.md) | Summary of the homelab Symphony Automation Runbook | `wiki/raw/runbook-symphony.md`, `~/homelab/docs/runbooks/automation/symphony.md` | 2026-06-09 |
| [sources/symphony-host-service-unit.md](sources/symphony-host-service-unit.md) | Live systemd unit snapshot — env block, dead OpenCode drift, secrets-via-env-file convention | `wiki/raw/symphony-host.service` | 2026-06-09 |

## Entities

| Page | Summary | Sources | Updated |
|------|---------|---------|---------|
| [entities/binding-homelab.md](entities/binding-homelab.md) | homelab Project Binding — full Role set, original Symphony target | `wiki/raw/bindings.yml` | 2026-06-09 |
| [entities/binding-trading.md](entities/binding-trading.md) | trading Project Binding — leaner Role set, multi-project demonstrator | `wiki/raw/bindings.yml` | 2026-06-09 |
| [entities/workflow-homelab.md](entities/workflow-homelab.md) | homelab `WORKFLOW.md` — medium-risk autonomy, plan/build/execute, excluded services, completion contract | `wiki/raw/workflow-homelab.md` | 2026-06-09 |
| [entities/workflow-trading.md](entities/workflow-trading.md) | trading `WORKFLOW.md` — Trading Safety Boundary, secrets-never-read, sandbox-only-by-default | `wiki/raw/workflow-trading.md` | 2026-06-09 |

## Concepts

| Page | Summary | Sources | Updated |
|------|---------|---------|---------|
| [concepts/symphony-engine.md](concepts/symphony-engine.md) | Engine model — core loop, Bindings, Mode, Agent, Workflow, Tracker abstraction, Run lifecycle, Landing | `wiki/raw/symphony-context.md` | 2026-06-09 |
| [concepts/symphony-operations.md](concepts/symphony-operations.md) | Operational model — service, restart ritual, scheduling, blocked reconciler, Telegram, failure pointers | `wiki/raw/runbook-symphony.md`, CLAUDE.md | 2026-06-09 |
| [concepts/tracker-contract.md](concepts/tracker-contract.md) | Tracker Contract — engine Roles, required/optional, data shape, resolvers | `wiki/raw/tracker_contract.py`, `wiki/raw/adr-0004-tracker-contract.md` | 2026-06-09 |
| [concepts/scheduler-loop.md](concepts/scheduler-loop.md) | `scheduler.py` — constants, semaphore concurrency, rate-limit cooldown, dirty-base approval, top-level coroutines | `scheduler.py` | 2026-06-09 |
| [concepts/agent-runner-and-worktree.md](concepts/agent-runner-and-worktree.md) | Pre-thin-engine — `run_worktree.py`, `ClaudeAgentAdapter`, worktree lifecycle. Superseded by `concepts/thin-engine-v2.md` for coding bindings. | `agent_runner.py`, `run_worktree.py` | 2026-06-09 |
| [concepts/thin-engine-v2.md](concepts/thin-engine-v2.md) | Thin engine v2 — no worktrees, PiAgentAdapter only, coding vs infra binding differences, provider/model config | `agent_runner.py`, `scheduler.py`, `config.py`, `main.py` | 2026-06-09 |
| [concepts/prompt-renderer.md](concepts/prompt-renderer.md) | `prompt_renderer.py` — variable substitution, Plane/Podium paths, comments/context rendering, Skill→Mode bridge | `prompt_renderer.py`, `skill_mode_map.py`, `tests/test_prompt_renderer_podium.py` | 2026-06-11 |
| [concepts/schedule-comment-grammar.md](concepts/schedule-comment-grammar.md) | `Symphony-Schedule:` / `Symphony-Schedule-Cancelled:` grammar, hard invariants, sort precedence, HTML normalisation | `schedule.py` | 2026-06-09 |
| [concepts/blocked-reconciler-implementation.md](concepts/blocked-reconciler-implementation.md) | `blocked_reconciler.py` — caps, regexes, `ReconcileRule` shape, default rule, skip conditions, log markers | `blocked_reconciler.py` | 2026-06-09 |
| [concepts/podium-tracker.md](concepts/podium-tracker.md) | Podium tracker impl — schema/state enums, db path, PATCH contract, seeding, and #019 SQLite TrackerAdapter + scheduler context writes | `web/api/schema.py`, `web/api/db.py`, `web/api/main.py`, `tracker_podium.py`, `tracker_adapter.py` | 2026-06-11 |

## Analyses

| Page | Summary | Sources | Updated |
|------|---------|---------|---------|
| [analyses/adr-0001-claude-tmux.md](analyses/adr-0001-claude-tmux.md) | ADR-0001 — Dispatch Claude through tmux send-keys, not print mode | `wiki/raw/adr-0001-claude-tmux.md` | 2026-06-09 |
| [analyses/thin-engine-e2e-test.md](analyses/thin-engine-e2e-test.md) | Thin engine E2E smoke test — dispatch lifecycle, code drift root cause, provider/model config, stale worktree cleanup | `wiki/raw/sessions/2026-06-09-thin-engine-e2e-test.md` | 2026-06-09 |
| [analyses/adr-0002-generalize-symphony.md](analyses/adr-0002-generalize-symphony.md) | ADR-0002 — Generalize Symphony behind adapter seams | `wiki/raw/adr-0002-generalize-symphony.md` | 2026-06-09 |
| [analyses/adr-0003-worktree-per-run.md](analyses/adr-0003-worktree-per-run.md) | ADR-0003 — Worktree-per-run with global concurrency cap | `wiki/raw/adr-0003-worktree-per-run.md` | 2026-06-09 |
| [analyses/adr-0004-tracker-contract.md](analyses/adr-0004-tracker-contract.md) | ADR-0004 — Role-based per-binding Tracker Contract | `wiki/raw/adr-0004-tracker-contract.md` | 2026-06-09 |
| [analyses/symphony-plan-history.md](analyses/symphony-plan-history.md) | Five plans under `plans/` — landed status, key decisions, open follow-ups | 5 plan raw files | 2026-06-09 |
| [analyses/brainstorm-pi-swap.md](analyses/brainstorm-pi-swap.md) | Pi-executor-swap brainstorm — rejected designs, silent-failure rationale, locked-decisions table | `wiki/raw/brainstorm-pi-swap.md` | 2026-06-09 |
| [analyses/pi-swap-review-specs.md](analyses/pi-swap-review-specs.md) | 4 reviewer PRD artifacts — multi-round audit discipline against the pi-swap plan | 4 spec PRD files | 2026-06-09 |
| [analyses/symphony-skills-index.md](analyses/symphony-skills-index.md) | 8 `symphony-*` Claude Code skills — lifecycle map and per-skill summary | 8 SKILL.md files | 2026-06-09 |
| [analyses/symphony-tests-index.md](analyses/symphony-tests-index.md) | 14 test files, 435 tests — coverage map and validation contract | `tests/*.py` | 2026-06-09 |
| [analyses/trading-smoke-rate-limit-debugging.md](analyses/trading-smoke-rate-limit-debugging.md) | Trading smoke debugging — post-agent Plane 429 recovery, shared cooldown, optional-label scan fix, conversation-mode landing-proof gap | session capture, `scheduler.py`, `prompt_renderer.py` | 2026-06-09 |
| [analyses/podium-014-new-issue-flow.md](analyses/podium-014-new-issue-flow.md) | Podium #014 — POST issues endpoint contract, INSERT OR IGNORE seeding pivot, /options dropdown endpoint, optimistic modal UX, cross-slice constraints for #015/#020 | `wiki/raw/sessions/2026-06-10-podium-014-new-issue-flow.md`, `web/api/main.py`, `web/api/seed.py` | 2026-06-10 |
| [analyses/podium-017-live-updates.md](analyses/podium-017-live-updates.md) | Podium #017 — WS /api/ws, in-process fanout, issue/run event contract, TanStack Query live cache updates, reconnect pill, optimistic-create race fix, last-write-wins decision | `web/api/main.py`, `web/frontend/components/QueryProvider.tsx`, `web/api/tests/test_websocket.py`, `web/frontend/tests/live-sync.spec.ts` | 2026-06-11 |
| [analyses/podium-018-auth.md](analyses/podium-018-auth.md) | Podium #018 — bcrypt shared-password auth, signed session cookie, API/WS auth gates, login/logout UI, set-password CLI, test-auth convention | `web/api/auth.py`, `web/api/main.py`, `web/frontend/components/AppShell.tsx`, `web/cli/podium.py` | 2026-06-11 |
| [analyses/adr-0005-replace-plane-with-podium.md](analyses/adr-0005-replace-plane-with-podium.md) | ADR-0005 — retire Plane, build Podium; Binding-is-Project, Run first-class table + startup reaper, Skill subsumes Mode, worktree opt-in, tracker:plane\|podium seam, sibling units, rejected alternatives, ADR-0001/2/3 reconciliation | `wiki/raw/adr-0005-replace-plane-with-podium.md`, `docs/adr/0005-replace-plane-with-podium.md` | 2026-06-10 |
| [analyses/analysis-session-020-cutover-smoke.md](analyses/analysis-session-020-cutover-smoke.md) | #020 trading→Podium cutover smoke — run-log finalization bug (adapter `db_path=None` → unwritable `/var/lib/symphony/runs` → PermissionError), `__post_init__` fix, run-log co-location convention, masked-test lesson, smoke evidence | `wiki/raw/sessions/2026-06-11-podium-020-cutover-smoke.md`, `tracker_podium.py`, `scheduler.py`, `web/api/db.py` | 2026-06-11 |

## Candidate Review Queue

Candidate rows are discoverability aids only; do not treat them as promoted knowledge. This project uses **auto-promotion** — candidates transit this queue briefly during ingest and are promoted by the agent after lint.

| Candidate | Summary | Sources | Created | Status |
|-----------|---------|---------|---------|--------|
_(empty — all candidates promoted or discarded)_
