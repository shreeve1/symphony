---
id: 124
title: Stall watchdog in _drain_rpc_events + dispatch wiring
status: in-progress
blocked_by: [123]
updated: 2026-06-25
actor: ralph
locks: [agent_runner]
priority: 1
created: 2026-06-25
---

## What to build

Install a silence watchdog inside `_drain_rpc_events` and wire stall detection through both local and remote dispatch paths.

1. **Watchdog in `_drain_rpc_events`:**
   - Add `stall_timeout_s: float = 900.0` keyword-only parameter (after `*`).
   - Track `last_event_time = clock()` before the `while True` loop.
   - After each successful `json.loads(line)`, update `last_event_time = clock()`.
   - At the top of the `while True` loop body, immediately after the existing 2h deadline check: when `clock() - last_event_time > stall_timeout_s`, take the same abort+kill path (`_send_rpc_abort` + `_terminate_process_group`) and return `_DrainResult(..., stalled=True, ...)`.

2. **Wire through `run_pi_rpc_agent`:**
   - Compute `stall_timeout_s = config.stall_timeout_ms / 1000`, pass to `_drain_rpc_events`.
   - After drain: if `drain.stalled`, build stderr as `STALL_WATCHDOG_SENTINEL + "\n" + "".join(drain.stderr_parts)`, return `AgentResult(-1, duration_ms, False, stdout, stderr)` (note: `timed_out=False` — stall is a liveness failure distinct from the 2h deadline).

3. **Wire through `run_remote_agent`:**
   - Identical: compute `stall_timeout_s` from config, pass to `_drain_rpc_events`, return watchdog-sentinel `AgentResult` on stall.

## Acceptance criteria

- [ ] Silence > `stall_timeout_s` → abort+kill path fires, `_DrainResult.stalled == True`
- [ ] Sparse events within `stall_timeout_s` → `stalled == False`, normal completion
- [ ] Stall check runs after 2h deadline check (2h fires first if both expired)
- [ ] `run_pi_rpc_agent` returns `AgentResult(exit_code=-1, timed_out=False, stderr starts with STALL_WATCHDOG_SENTINEL)` on stall
- [ ] `run_remote_agent` returns same sentinel contract on stall
- [ ] `stall_timeout_s` parameter is keyword-only (doesn't break existing callers)
- [ ] All existing tests in `tests/test_agent_runner.py` still pass

## Verification

`uv run pytest tests/test_agent_runner.py -x -q`

**Test notes for implementer:** `FakeRpcProcess` (fileless `io.StringIO`) cannot trigger stall because its `read_line` returns `""` (EOF) on exhaustion, never `(None, False)`. Stall tests must pass hand-crafted `read_line` callables that return `(None, False)` repeatedly for the silence interval, then `(event_json, False)` for events. Extract a reusable `_stall_read_line` factory. Custom `clock` (e.g. `iter([0.0, 0.0, 900.0, 900.1]).__next__`) advances past `stall_timeout_s` between `read_line` calls without actual sleep.

## Blocked by

- Blocked by #123
