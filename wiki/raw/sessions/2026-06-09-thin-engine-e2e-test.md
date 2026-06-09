# Session Capture: Thin Engine E2E Smoke Test + Service Restart

- Date: 2026-06-09
- Purpose: Verify thin engine v2 dispatch lifecycle end-to-end and deploy thin engine commit to running service
- Scope: E2E lifecycle verification, root cause of running old code, provider/model config, service restart, stale worktree cleanup

## Durable Facts

- The thin engine commit `e73e924` (feat: thin engine — remove worktrees, add coding binding type) landed at 18:43 UTC but the running service was started at 04:39 UTC and never restarted. The running code was at `c4944be` (pre-thin-engine). — Evidence: `systemctl show symphony-host.service --property=ActiveEnterTimestamp`, `git log --oneline e73e924 --format="%H %ai %s"`
- Service restart was required to pick up the thin engine code. Verified post-restart: code_sha=e73e924, reconcile cleared 0 stale runs per binding, dispatch loop healthy. — Evidence: journalctl output showing `symphony_started service=symphony code_sha=e73e924 bindings=2`
- Provider/model on the unit is `openai-codex/gpt-5.5` via `SYMPHONY_PI_PROVIDER` and `SYMPHONY_PI_MODEL` env vars. Not `pi/zai/glm-5.1:high`. — Evidence: `systemctl show symphony-host.service --property=Environment`
- Full smoke lifecycle completed with old code: issue_claimed → agent_exited(0) → state_transitioned(in-review) → dispatch_completed(true). Issue transitioned Todo → Running → In Review → Done. — Evidence: journalctl, Plane API reads
- Stale worktree `run-ef2d127d` from a pre-thin-engine run (Jun 9 02:02) existed in trading worktrees dir. Removed via `git worktree remove`. Worktrees directory now empty. — Evidence: `git worktree list`, `ls -la` before/after
- The `run_worktree.py` module does not exist in commit `e73e924`. The `ClaudeAgentAdapter` class does not exist in the current `agent_runner.py`. The `RoutingAgentAdapter` now only wraps `pi_adapter` (no claude, no worktree_path parameter). — Evidence: file search, grep on current codebase

## Decisions

- No decision needed for provider/model change — James chose to keep `openai-codex/gpt-5.5` as-is.
- James approved service restart with pre-sanity ritual — executed successfully.
- James approved stale worktree cleanup.

## Evidence

- `git log --oneline -5` — shows e73e924 landed at 18:43, service started at 04:39
- `journalctl -u symphony-host.service` — shows old PID 38149 running pre-thin-engine code, new PID 1474281 running e73e924
- `systemctl show symphony-host.service --property=Environment` — SYMPHONY_PI_PROVIDER=openai-codex, SYMPHONY_PI_MODEL=gpt-5.5, PI_BIN=/home/james/.npm-global/bin/pi
- Plane API responses — issue b0b79316 lifecycle: created in Todo, PATCH to Running, completion comment + transition to In Review, then to Done
- `git -C /home/james/trading/crypto-trading-agents worktree remove` — cleaned stale worktree run-ef2d127d
- `grep -rn "run_worktree\|ClaudeAgentAdapter" /home/james/symphony/ --include="*.py"` — zero matches in current codebase confirming removal

## Exclusions

- No secrets, credentials, .env contents, or personal data captured.
- No full transcript — only durable facts and evidence references.
- Normal dispatch loop entries (no-candidates) not captured — routine.

## Open Questions And Follow-Ups

- The wiki concept page `agent-runner-and-worktree.md` is now substantially stale — documents deleted modules (run_worktree.py, ClaudeAgentAdapter) and old worktree-based behavior. Needs update for thin engine v2.
- Several CLAIMS.md entries reference worktree-specific behavior that coding bindings no longer use (C-0009, C-0018, C-0019, C-0020, C-0040, C-0041, C-0042, C-0044). Should be annotated as superseded or restricted to infra bindings.
- If provider/model should eventually be switched to pi/zai, the unit needs `SYMPHONY_PI_PROVIDER` and `SYMPHONY_PI_MODEL` changes.
