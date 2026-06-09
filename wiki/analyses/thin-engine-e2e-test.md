---
title: Thin Engine E2E Smoke Test
type: analysis
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - wiki/raw/sessions/2026-06-09-thin-engine-e2e-test.md
  - scheduler.py
  - agent_runner.py
  - config.py
  - /etc/systemd/system/symphony-host.service
confidence: high
tags: [thin-engine, e2e, smoke-test, worktree, dispatch, provider]
---
# Thin Engine E2E Smoke Test

## Summary

E2E dispatch test of the trading (coding) binding. Smoke ticket was filed in Plane (Todo), picked up by Symphony, dispatched to pi, completed with exit code 0, and transitioned to In Review — then archived to Done.

## Key Finding: Code Drift

The thin engine commit `e73e924` (18:43 UTC) had not been deployed to the running service (started at 04:39 UTC). The first dispatch ran against the old pre-thin-engine code, which created worktrees and used the full legacy lifecycle. After restart with `e73e924`, the service runs thin engine code correctly. [source: wiki/raw/sessions/2026-06-09-thin-engine-e2e-test.md]

### Lesson

Always check `code_sha` at startup vs `git log` HEAD before diagnosing behavior that should have changed. The `symphony_started` log line includes `code_sha=<sha>` and `bindings=<n>` for this purpose.

## Service Restart

- Pre-sanity: HEAD=e73e924, clean working tree, old PID 38149 running since 04:39
- Restart executed via `sudo systemctl restart symphony-host.service`
- Post-restart: PID 1474281, `code_sha=e73e924`, `bindings=2`, reconcile cleared 0 stale runs per binding, dispatch loop healthy with no errors [source: journalctl]

## Provider/Model Configuration

Unit env: `SYMPHONY_PI_PROVIDER=openai-codex`, `SYMPHONY_PI_MODEL=gpt-5.5`, `PI_BIN=/home/james/.npm-global/bin/pi`. Config.py defaults (`zai/glm-5.1:high`) are unit-overridden. [source: systemctl show symphony-host.service --property=Environment]

## Thin Engine Code Changes (e73e924)

Confirmed codebase changes:
- `run_worktree.py` — deleted entirely. No worktree creation, listing, removal, or naming functions exist.
- `ClaudeAgentAdapter` — deleted from `agent_runner.py`. Only `PiAgentAdapter` and simplified `RoutingAgentAdapter` remain.
- `RoutingAgentAdapter` — no longer takes `worktree_path` parameter. Hardwired to pi only.
- `agent_runner.run_agent()` — uses `cwd = str(config.homelab_repo_path)` (repo dir, not worktree path).
- `scheduler.run_tick()` — uses `is_coding` to gate: blocked reconciler, scheduled release, approval policy, and schedule skip. But the worktree creation code was in `_dispatch_one` which was also removed.

## Stale Worktree Cleanup

Stale worktree `run-ef2d127d` from pre-thin-engine run (Jun 9 02:02) found in trading worktrees directory. Removed via `git -C /home/james/trading/crypto-trading-agents worktree remove <path>`. [source: bash output]

## Related Claims

- C-0009 (Run Worktree) — superseded for coding bindings; infra bindings may still use worktrees if code readds them
- C-0018 (Worktree-per-run replaces global flock) — superseded per above
- C-0019 (Durable signals from worktree/tmux) — no longer applicable for coding; infra bindings TBD
- C-0020 (Plan→build git-ref handoff) — superseded for coding bindings
- C-0040 through C-0044 (worktree naming, claude adapter) — code deleted from current source
