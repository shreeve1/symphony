---
title: Symphony plan history
type: analysis
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - wiki/raw/plan-refactor-move-symphony-to-home.md
  - wiki/raw/plan-operational-improvements.md
  - wiki/raw/plan-pi-executor-swap.md
  - wiki/raw/plan-plan-approve-workflow.md
  - wiki/raw/plan-ticket-scheduling.md
confidence: medium
tags: [plans, history, refactor, executor-swap, scheduling, plan-approve, lock-file, telegram]
---

# Symphony plan history

Five plans live under `plans/` and document landed or in-flight Symphony work. Landed status is verified against `git log`. Each plan's full text is preserved in `wiki/raw/`.

## Status verification

`git log --all --oneline -- plans/` shows commits:
- `b1b5a3f chore: ignore Symphony plans`
- `8af5dab feat: swap Symphony executor to pi`
- `36352f9 feat: add Symphony ticket scheduling`

`98c6359 refactor: relocate to /home/james/symphony; fix hardcoded test paths` lands the move plan.

## Plans

### refactor-move-symphony-to-home

**Status: landed** (commit `98c6359`).

Move Symphony source repo from `/home/james/plane/symphony` to `/home/james/symphony`. Move the env file `/home/james/plane/symphony-host.env` and its `.bak` sibling alongside it. Update every live reference: systemd unit, in-repo hardcoded test paths, `~/.claude` skill files, CLAUDE.md home/plane guides, homelab runbook, host doc. Plane-stack files (`docker-compose.yml`, `variables.env`, `provision_plane.py`) stay in `/home/james/plane/` [source: wiki/raw/plan-refactor-move-symphony-to-home.md#22-30].

v2 incorporates 4 Critical + 4 Warning findings from `/dev-review-claude`: added `telegram-alert@.service` to systemd edit set, added third commit in dotfiles (skill files are symlinks into `~/dotfiles/`), pre-mv CWD guard, widened final reference sweep for tilde-form refs, `systemd-analyze verify` before `daemon-reload`, stale tmux pane enumeration, post-commit rollback branch, additions to `~/dotfiles/.codex/config.toml` and homelab OpenCode `PlaneTicket` skill. Final shape: 59 implementation tasks + 16 test tasks [source: wiki/raw/plan-refactor-move-symphony-to-home.md#3-13].

### symphony-operational-improvements

**Status: partially landed; verify residual gaps**.

Three operational gaps in Symphony at the time of writing [source: wiki/raw/plan-operational-improvements.md#5-9]:

1. **Agent stderr captured but never surfaced** — `AgentResult` has `stderr` but completion paths only use `stdout`. Real errors hide in stderr.
2. **No concurrency guard across containers** — `/tmp/symphony.lock` is inside the container; two containers each have own `/tmp`, both can claim same issue. (Note: now host-native via `symphony-host.service`; lock is `/run/symphony/symphony.lock` per `SYMPHONY_LOCK_PATH`. Container concern likely moot.)
3. **Build mode relies on agent reading comment history** — `plane_cli.py` had no `plane comments` command. Agent must infer from issue description alone.

Solution approach: `_format_report()` splits stdout/stderr into separate fenced blocks; `from_env()` derives `lock_path` from `homelab_repo_path` when `SYMPHONY_LOCK_PATH` not set; add `plane comments` command oldest-first [source: wiki/raw/plan-operational-improvements.md#21-25].

Verify `plane comments` exists in `plane_cli.py` and `stderr` is surfaced before treating as fully landed.

### symphony-pi-executor-swap

**Status: landed** (commit `8af5dab`).

Replace OpenCode entirely as Symphony's coding-agent executor with locally installed `pi` CLI (`@mariozechner/pi-coding-agent`, v0.74.0 at `/home/james/.npm-global/bin/pi`). Symphony dispatches via `pi --print --no-session --provider zai --model glm-5.1:high <prompt>` from the configured homelab repo working directory. Same Plane state-transition guarantees as before, no OpenCode runtime dependency, explicit guardrails for pi auth/model silent failures [source: wiki/raw/plan-pi-executor-swap.md#5-9].

Key guardrail rationale: pi can exit 0 with empty stdout/stderr on auth or model misconfiguration; without explicit detection the scheduler would treat it as a successful no-op [source: wiki/raw/plan-pi-executor-swap.md#15].

Revision: brainstorm locked `--no-context-files` but Codex caught that `WORKFLOW.md` line 27 depends on homelab `AGENTS.md` safety rules. Final decision drops `--no-context-files` so pi loads `AGENTS.md` / `CLAUDE.md` from the homelab repo [source: wiki/raw/plan-pi-executor-swap.md#21-25].

Out of scope: `pi --mode json`, label-driven AGENTS.md overlays, removing `CLIPROXY_API_KEY` from live env.

### symphony-plan-approve-workflow

**Status: landed** (predates current ADR-0004; lives under the original homelab-owned `PlaneLabel` enum).

Label-driven plan/approval workflow: three labels (`plan`, `build`, `approved`) enable a two-phase issue lifecycle [source: wiki/raw/plan-plan-approve-workflow.md#5-9]:

1. **plan** mode — Symphony claims issue, renders plan-mode prompt (no implementation allowed), runs agent, on completion forces issue to `In Review` and adds `approval-required`.
2. James reviews, removes `approval-required`, adds `build`, moves back to `Todo`.
3. **build** mode — Symphony picks it up again, executes plan, completes normally.

Critical fixes called out in plan [source: wiki/raw/plan-plan-approve-workflow.md, tail]:

- Plane returns UUIDs in label arrays but poller compared names → added UUID→name mapping via `label_ids`.
- `repo_dirty` check moved after mode resolution; plan mode skips it (agent must not modify repo in plan mode).
- Plan-mode agent posts findings as Plane comment only; no plan file written to repo (avoids dirty-worktree deadlock).
- `_extract_labels` now resolves UUIDs → names using `label_ids` reverse map.
- `_resolve_mode` accepts UUID inputs, resolves internally.
- Prompt renderer prepends simple MODE header (no section parser needed).
- `add_labels` uses GET-merge-PATCH to preserve existing labels.
- `FakeTransport` needs `labels` tracking and GET support for tests.

Plan-mode comment-only artifact path is now incompatible with [ADR-0003](adr-0003-worktree-per-run.md)'s worktree-per-run model — superseded by the git-ref handoff (plan branch carries `plans/<slug>.md`).

### symphony-ticket-scheduling

**Status: landed** (commit `36352f9`).

One-shot, ticket-native scheduling. Agent/CLI scheduling uses a dedicated `scheduled` Plane label plus append-only structured comments. James can also add only the `scheduled` label; label-only scheduled tickets default to the next 12am-6am America/Los_Angeles maintenance window. A scheduled ticket remains `Todo + scheduled` until its `not_before` time, then Symphony releases exactly one due ticket per tick, removes the `scheduled` label, writes an audit comment, dispatches through normal claim/run/finalize flow [source: wiki/raw/plan-ticket-scheduling.md#5-7].

Notes [source: wiki/raw/plan-ticket-scheduling.md, tail]:

- Plan intentionally does not create Plane labels automatically; label creation/discovery is a live Plane/admin prerequisite, approved separately.
- Recurring schedules out of scope — use Windmill, cron, or patrol systems. (Windmill since decommissioned; Temporal carries that role now per home CLAUDE.md.)
- `not_after` is advisory only. Hard invariant: never execute before `not_before`.
- Scheduling allowed on any Symphony ticket; no domain-label gate.
- Schedule comments alone do not activate scheduling. Manual label-only schedules require the `scheduled` label and use the next 12am-6am PT maintenance window when no valid schedule comment exists.

## Open follow-ups (not in any single plan)

- Verify `symphony-operational-improvements` items 1 + 3 (stderr surfacing, `plane comments`) actually shipped against current code.
- Confirm `repo_dirty` skip-in-plan-mode logic survives the worktree-per-run refactor (plan mode now writes to ephemeral branch instead of a Plane comment in current model).

## Related

- [ADR-0001](adr-0001-claude-tmux.md), [ADR-0002](adr-0002-generalize-symphony.md), [ADR-0003](adr-0003-worktree-per-run.md), [ADR-0004](adr-0004-tracker-contract.md)
- [Symphony operations](../concepts/symphony-operations.md)
