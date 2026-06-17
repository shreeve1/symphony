---
id: 084
title: Run-end steer-close guard (no accepted-but-lost steer)
status: done
blocked_by: [83, 79]
parent: null
priority: 0
created: 2026-06-17
updated: 2026-06-17
actor: ralph
---

## What to build

Close the adapter-return-to-finalization window. The scheduler keeps a run in `running` state after `run_claude_agent` returns until `_finish_run_record` runs later, so the steer endpoint can ACCEPT a steer in that window — it lands in the queue after the supervised loop already exited and is never delivered (acknowledged-but-lost). Flip the run out of the steerable state immediately on adapter return so the endpoint rejects such steers.

Source: `plans/warm-claude-session-and-send-keys-steer.md` task 5.7 (round-3 W2 fix).

## What to build (detail)

- Immediately on agent return (before result/verdict processing in `scheduler/__init__.py`), flip the run out of the steerable state — set `latest_run_state` to a non-`running` value OR write a per-run "steering closed" marker the endpoint checks.
- The steer endpoint (`web/api/main.py`) must then reject (409) any steer once the supervised loop has exited, for both pi RPC and Claude.

## Acceptance criteria

- [x] A steer POSTed after the adapter returns but before run finalization is rejected (409), not silently queued.
- [x] A steer during a genuinely live run is still accepted (no regression to #083 / pi RPC steering).
- [x] The guard applies uniformly to pi RPC and Claude runs.

## Verification

`uv run pytest tests/test_scheduler.py tests/test_agent_runner.py web/api/tests/test_steer.py` and `uv run python -m py_compile scheduler/__init__.py web/api/main.py`

## Implementation Notes

Added `_close_run_record_steering` so `run_tick` updates the Run row to `succeeded` or `failed` immediately after the adapter returns and before terminal classification adds comments or transitions the Issue. Added scheduler coverage proving the projection is closed before terminal side effects, plus steer endpoint coverage proving non-running Run rows reject both pi and Claude steers.

## Blocked by

- Blocked by #83 (steer endpoint accepts Claude) and #79 (steer delivery loop).
