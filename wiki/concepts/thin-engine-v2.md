---
title: Thin Engine v2 — Agent Runner
type: concept
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - agent_runner.py (current)
  - scheduler.py (current lines 493, 625-825)
  - config.py (current)
  - main.py (current)
  - wiki/raw/sessions/2026-06-09-thin-engine-e2e-test.md
confidence: high
tags: [thin-engine, agent-runner, coding-binding, pi-adapter, no-worktree]
supersedes: wiki/concepts/agent-runner-and-worktree.md
---
# Thin Engine v2 — Agent Runner

Thin engine v2 (commit `e73e924`) strips worktrees, Claude dispatch, auto-commit, and Done landing from coding bindings. Only PiAgentAdapter remains active.

## Architecture Changes

### Deleted Modules

| Module | Status | Purpose |
|--------|--------|---------|
| `run_worktree.py` | deleted | worktree creation, listing, removal, tmux helpers |
| `ClaudeAgentAdapter` | deleted | tmux-based claude dispatch per ADR-0001 |
| `_run_id_from_identifier` | deleted | deterministic run_id (sha256 hash) |
| `list_worktrees` | deleted | git worktree enumeration |

### Changed Modules

**`agent_runner.py`**:
- `RoutingAgentAdapter` now wraps only `pi_adapter` — no claude branch, no `worktree_path` parameter. Always routes to pi.
- `run_agent()` uses `cwd = str(config.homelab_repo_path)` (repo directory) rather than a worktree path. [source: agent_runner.py#216]
- `PiAgentAdapter` unchanged — still uses `subprocess.Popen` + `process.communicate(timeout=...)`.
- `verify_pi_support` unchanged — two-step probe remains.

**`main.py`**:
- No longer references worktree, Claude, or run_worktree modules.
- `_build_binding_runtime` creates `RoutingAgentAdapter(binding, pi_adapter=PiAgentAdapter(binding_config))`. [source: main.py#52-70]

**`scheduler.py`**:
- `run_tick()` gates schedule, blocked reconciler, and approval policy behind `is_coding` (line 493).
- `_dispatch_one()` no longer creates worktrees — removed in thin engine.
- Coding completion comment is shorter: does not include rerun instructions that reference worktrees. [source: scheduler.py#786-789]

**`config.py`**:
- `worktrees_root` still computed in `__post_init__` and `for_binding()` but no longer consumed by any running code. Drift. [source: config.py#149-155, #240]
- `for_binding()` still sets `worktrees_root` — clean-up candidate but harmless.

## Agent Dispatch Flow (thin engine)

1. `scheduler.run_tick()` selects candidate issue from Todo state
2. `_dispatch_one()` renders prompt, transitions issue to Running, posts claim comment
3. `agent_runner.run_agent()` is called with `cwd = config.homelab_repo_path` (repo checkout, no worktree)
4. pi subprocess runs in repo directory with `--print --no-session --provider <p> --model <m>`
5. On completion: scheduler reads stdout for SYMPHONY_RESULT marker, posts completion comment
6. Issue transitions to In Review (always — no Done→InReview step for coding)

## Provider/Model Configuration

Provider and model come from `SymphonyConfig.pi_provider` and `SymphonyConfig.pi_model`, which read from env `SYMPHONY_PI_PROVIDER` and `SYMPHONY_PI_MODEL`. **Not** `config.py` defaults (`zai/glm-5.1:high`) — unit env overrides apply.

Current unit: `SYMPHONY_PI_PROVIDER=openai-codex`, `SYMPHONY_PI_MODEL=gpt-5.5`. [source: systemctl show]

## Coding vs Infra Binding Differences

| Feature | infra | coding |
|---------|-------|--------|
| Worktree | old code only | never |
| Schedule | yes | skip (`is_coding` gate) |
| Blocked reconciler | yes (default) | skip (`is_coding` gate) |
| Approval gate | configurable | skip (`is_coding` gate) |
| Agent dispatch | pi only (v2) | pi only (v2) |
| Completion transition | In Review | In Review (no Done→InReview step) |

## Env Variables and Constructor Overrides

The SymphonyConfig constructor defaults pi_provider="zai", pi_model="glm-5.1:high". At runtime these are overridden by environment variables sourced from the systemd unit. The unit get their values from /home/james/symphony-host.env. Run `systemctl show symphony-host.service --property=Environment` for live values.

## Related

- [E2E test analysis](../candidates/analysis-thin-engine-e2e-test.md) (candidate)
- [scheduler.py concepts](scheduler-loop.md) (existing promoted — needs is_coding section)
- [agent-runner-and-worktree.md](../concepts/agent-runner-and-worktree.md) (existing promoted — stale, covered by this candidate)
- [binding-trading entity](../entities/binding-trading.md) (existing promoted — trading uses coding binding_type)

> **2026-06-12 update:** Podium dispatch provider/model now resolve per-issue from `models.yml` via the scheduler dispatch gate; `SYMPHONY_PI_PROVIDER`/`SYMPHONY_PI_MODEL` are a legacy Plane-path fallback. See [../analyses/podium-issue-dispatch-contract.md](../analyses/podium-issue-dispatch-contract.md).
