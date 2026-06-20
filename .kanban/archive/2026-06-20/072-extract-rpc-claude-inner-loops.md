---
id: 072
title: Extract RPC and Claude dispatch inner loops
status: done
blocked_by: []
parent: null
priority: 0
created: 2026-06-17
updated: 2026-06-17
actor: ralph
action_reviewed: 2026-06-17
---

## What to build

Finding L2-05 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`). Two 200+-LOC dispatch functions each own setup + streaming/poll loop + teardown in one body: `run_pi_rpc_agent` (`agent_runner.py:572-789`, JSONL event loop `:675-748`) and `run_claude_agent` (`claude_runner.py:362-571`, tmux launch + ready-wait + paste + idle/nudge poll loop `:490-569`).

Extract the inner loops as named steps so each function reads setup → loop → teardown:
- `_drain_rpc_events(process, deadline, run_id, ...)` returning parts + exit_code.
- `_poll_claude_until_done(...)` returning `AgentResult | None`.

Independent of the scheduler decomposition — rides the same wave. (If #060/#062 have repointed `agent_runner` helpers, build on top of those.)

## Acceptance criteria

- [x] `_drain_rpc_events` extracted; `run_pi_rpc_agent` reads setup → loop → teardown.
- [x] `_poll_claude_until_done` extracted; `run_claude_agent` reads setup → loop → teardown.
- [x] Behavior unchanged; `uv run pytest` passes.

## Verification

`uv run pytest`

Dispatch executor on the live path. Before this issue is marked done, James runs the `symphony-restart` skill and confirms `symphony_started`, `reconcile_startup_*`, and `dispatch_completed` in the journal.

## Blocked by

None — can start immediately.

## Implementation Notes

- Extracted `_drain_rpc_events(process, deadline, run_id, ...)` returning `_DrainResult` from `agent_runner.run_pi_rpc_agent`, with steer forwarding, JSONL event parsing, timeout abort, and event-exit classification preserved.
- Extracted `_poll_claude_until_done(...)` returning `AgentResult | None` from `claude_runner.run_claude_agent`, with done-file handling, session liveness, idle detection, nudges, and timeout handling preserved.
- Verified `uv run pytest -q` (887 passed, 2 skipped), `uv run ruff check agent_runner.py claude_runner.py`, `git diff --check`, touched-file LSP diagnostics, fresh review `RALPH_REVIEW: PASS`, and live `symphony-host.service` restart lifecycle evidence on `code_sha=5cc9b4a`.
