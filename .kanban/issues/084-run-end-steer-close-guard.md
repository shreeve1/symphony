---
id: 084
title: Run-end steer-close guard (no accepted-but-lost steer)
status: pending
blocked_by: [83, 79]
parent: null
priority: 0
created: 2026-06-17
---

## What to build

Close the adapter-return-to-finalization window. The scheduler keeps a run in `running` state after `run_claude_agent` returns until `_finish_run_record` runs later, so the steer endpoint can ACCEPT a steer in that window — it lands in the queue after the supervised loop already exited and is never delivered (acknowledged-but-lost). Flip the run out of the steerable state immediately on adapter return so the endpoint rejects such steers.

Source: `plans/warm-claude-session-and-send-keys-steer.md` task 5.7 (round-3 W2 fix).

## What to build (detail)

- Immediately on `run_claude_agent` return (before result/verdict processing at `scheduler.py:1512-1516`), flip the run out of the steerable state — set `latest_run_state` to a non-`running` value (e.g. `completing`) OR write a per-run "steering closed" marker the endpoint checks.
- The steer endpoint (`web/api/main.py:1245-1261`) must then reject (409) any steer once the supervised loop has exited, for both pi RPC and Claude.

## Acceptance criteria

- [ ] A steer POSTed after the adapter returns but before run finalization is rejected (409), not silently queued.
- [ ] A steer during a genuinely live run is still accepted (no regression to #083 / pi RPC steering).
- [ ] The guard applies uniformly to pi RPC and Claude runs.

## Verification

`uv run pytest tests/test_scheduler.py tests/test_agent_runner.py` and `uv run python -m py_compile scheduler.py web/api/main.py`

## Blocked by

- Blocked by #83 (steer endpoint accepts Claude) and #79 (steer delivery loop).
