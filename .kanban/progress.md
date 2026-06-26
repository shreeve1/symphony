# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

## #123 Config + data-type scaffolding for stall watchdog — 2026-06-25

**What changed:** Added stall watchdog scaffolding only: config timeout field/env/repr, `_DrainResult.stalled`, and shared sentinel constant.
**Files:** config.py, agent_runner.py, redispatch_core.py, .kanban/issues/123-config-stall-scaffolding.md
**Decisions:** Kept #123 behavior-free; runtime watchdog behavior remains for #124/#125.
**Conventions established:** Verification commands should be self-contained and not rely on ambient service env.
**Notes for next iteration:** #124 can consume `config.stall_timeout_ms`, `_DrainResult.stalled`, and `STALL_WATCHDOG_SENTINEL`.
**Action review:** Re-read diff from `041fbb067c079fc8f0d5ec40997d45ee18b07f00`, verified all acceptance criteria, ran the exact verification block, and checked LSP diagnostics for touched Python files (no diagnostics).

## #124 Stall watchdog in _drain_rpc_events + dispatch wiring — 2026-06-25

**What changed:** Added a silence watchdog to `_drain_rpc_events`, passed `config.stall_timeout_ms` into local and remote Pi RPC drains, and returns `SYMPHONY_STALL_WATCHDOG` stderr sentinels with `timed_out=False` on stalls.
**Files:** `agent_runner.py`, `tests/test_agent_runner.py`, `tests/test_remote_agent.py`, `.kanban/issues/124-stall-watchdog-dispatch.md`.
**Decisions:** Kept stall distinct from the 2h deadline: deadline sets `timed_out=True`; stall sets `timed_out=False` and uses the watchdog sentinel.
**Conventions established:** RPC liveness tests should inject custom `read_line` callables instead of relying on `FakeRpcProcess` EOF behavior.
**Notes for next iteration:** Downstream terminal classification can key on `SYMPHONY_STALL_WATCHDOG` without conflating it with timeout handling.

## #125 Stall retry markers + counter + combined ceiling + _classify_terminal path — 2026-06-26

**What changed:** Added stall retry marker/counter helpers, scheduler transient-retry re-exports, combined retry ceiling pre-checks, and stall retry classification for implement/review dispatch.
**Files:** `redispatch_core.py`, `scheduler/transient_retry.py`, `scheduler/__init__.py`, `tests/test_transient_retry.py`, `tests/test_scheduler.py`, `.kanban/issues/125-stall-retry-classify.md`.
**Decisions:** Stall retries are separate from timeout/transient matching (`SYMPHONY_STALL_WATCHDOG` is not transient), get one retry, and share a combined ceiling of three total retry markers.
**Conventions established:** Review stall retries keep the issue in review and add `RELAND_PENDING`; implement stall retries return to todo.
**Action review:** Fresh reviewer diffed from `e49df7163ed001a549d417e5a501b72aab9c61a8`, ran `uv run pytest tests/test_transient_retry.py tests/test_scheduler.py -x -q`, and returned `RALPH_REVIEW: PASS`.
