"""Scheduler loop concern module.

Loop lifecycle (run_loop, _sleep_or_wake, _wait_for_tasks_or_wake) moved from
scheduler/__init__.py.  Functions still in __init__ (_dispatch_one,
_sweep_persistent_claude_sessions, _fixed_now) are imported lazily.

WAKE_SENTINEL_CHECK_INTERVAL_S and LOG_RETENTION_INTERVAL are local constants
to avoid a circular dependency on __init__ for trivial values.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from agent_runner import AgentAdapter
from config import ProjectBinding, SymphonyConfig
from notifier import TelegramNotifier
from tracker_adapter import TrackerAdapter
from tracker_types import CandidateIssue
from .bindings import binding_from_config as _binding_from_config
from .dispatch_state import (
    _cooldown_remaining_s,
    _effective_run_cap,
    _new_dispatch_state,
)
from .reconcile import run_log_retention as _run_log_retention

LOGGER = logging.getLogger(__name__)

WAKE_SENTINEL_CHECK_INTERVAL_S = 1.0
LOG_RETENTION_INTERVAL = timedelta(hours=24)


async def _sleep_or_wake(
    timeout: float,
    *,
    sleep: Callable[[float], Any] | None = None,
    consume_wake: Callable[[], bool] | None = None,
    check_interval: float = WAKE_SENTINEL_CHECK_INTERVAL_S,
) -> bool:
    """Sleep up to ``timeout`` seconds, returning early when a wake is consumed."""

    from . import consume_wake_sentinel  # noqa: F811

    sleep_fn = sleep or asyncio.sleep
    consume_fn = consume_wake or consume_wake_sentinel
    if consume_fn():
        return True
    remaining = max(0.0, timeout)
    while remaining > 0:
        delay = min(remaining, check_interval)
        await sleep_fn(delay)
        if consume_fn():
            return True
        remaining -= delay
    return False


async def _wait_for_tasks_or_wake(
    tasks: set[asyncio.Task],
    timeout: float,
) -> tuple[set[asyncio.Task], set[asyncio.Task], bool]:
    """Wait for a task completion or a wake sentinel, without busy-looping."""

    from . import consume_wake_sentinel  # noqa: F811

    pending = set(tasks)
    remaining = max(0.0, timeout)
    if consume_wake_sentinel():
        return set(), pending, True
    while remaining > 0:
        delay = min(remaining, WAKE_SENTINEL_CHECK_INTERVAL_S)
        done, pending = await asyncio.wait(
            pending,
            timeout=delay,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if done:
            return set(done), set(pending), False
        if consume_wake_sentinel():
            return set(), set(pending), True
        remaining -= delay
    return set(), set(pending), False


async def run_loop(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    *,
    agent_runner: AgentAdapter,
    render_prompt: Callable[[CandidateIssue], str],
    notifier: TelegramNotifier | None = None,
    binding: ProjectBinding | None = None,
    compaction_agent_runner: AgentAdapter | None = None,
) -> None:
    """Run the concurrent dispatcher forever, sleeping between dispatches.

    The dispatcher launches up to run_cap Runs concurrently as async tasks.
    Each task holds its semaphore slot until the Run completes
    (on all exit paths — verdict, crash, timeout).
    Per-tick single-run serialization is removed; the semaphore cap is the only
    concurrency governor.
    """

    from . import (  # noqa: F811
        TickResult,
        _dispatch_one,
        _fixed_now,
        _sleep_or_wake,
        _sweep_persistent_claude_sessions,
        _wait_for_tasks_or_wake,
    )

    next_blocked_reconcile_at = datetime.now(UTC)
    next_log_retention_at = datetime.now(UTC) + LOG_RETENTION_INTERVAL
    active_tasks: set[asyncio.Task[TickResult]] = set()
    loop_binding = binding or _binding_from_config(config)
    state = _new_dispatch_state(config, binding=loop_binding)
    effective_cap = _effective_run_cap(config, loop_binding)

    while True:
        now_dt = datetime.now(UTC)
        if loop_binding is not None and loop_binding.claude_persist:
            try:
                await _sweep_persistent_claude_sessions(
                    loop_binding,
                    adapter,
                    now=now_dt,
                    idle_ttl_s=config.claude_persist_idle_ttl_s,
                    max_live=config.claude_persist_max_live,
                )
            except Exception as exc:
                LOGGER.warning(
                    "claude_persist_sweep_failed binding=%s error=%s",
                    loop_binding.name,
                    exc,
                    exc_info=True,
                )
        run_blocked_reconcile = now_dt >= next_blocked_reconcile_at
        if now_dt >= next_log_retention_at:
            next_log_retention_at = now_dt + LOG_RETENTION_INTERVAL
            retention_kwargs = {"binding": binding} if binding is not None else {}
            await _run_log_retention(
                config,
                adapter,
                now=_fixed_now(now_dt),
                **retention_kwargs,
            )

        # Reap completed tasks and propagate their log lines.
        done = {t for t in active_tasks if t.done()}
        for task in done:
            try:
                result = task.result()
            except Exception as exc:
                LOGGER.warning("dispatch_failed error=%s", exc, exc_info=True)
                continue
            LOGGER.info(
                "dispatch_completed dispatched=%s reason=%s issue_id=%s",
                str(result.dispatched).lower(),
                result.reason,
                result.issue_id or "",
            )
        active_tasks -= done
        cooldown_remaining = _cooldown_remaining_s(
            state, now=lambda now_dt=now_dt: now_dt
        )

        if run_blocked_reconcile:
            next_blocked_reconcile_at = now_dt + timedelta(
                milliseconds=config.blocked_reconciler_interval_ms
            )

        # Start one probe per poll cycle.  The probe may claim one candidate and
        # hold a semaphore slot for the whole Run.  Starting run_cap probes at
        # once duplicates Plane pagination/reconciler work while idle and can
        # trip Plane 429s; subsequent cycles fill remaining slots while long
        # Runs are active.
        slots_available = effective_cap - len(active_tasks)
        if slots_available > 0 and cooldown_remaining <= 0:
            dispatch_kwargs: dict[str, Any] = {}
            if binding is not None:
                dispatch_kwargs["binding"] = binding
            if compaction_agent_runner is not None:
                dispatch_kwargs["compaction_agent_runner"] = compaction_agent_runner
            task = asyncio.create_task(
                _dispatch_one(
                    config,
                    adapter,
                    agent_runner,
                    render_prompt,
                    notifier,
                    run_blocked_reconcile,
                    state,
                    **dispatch_kwargs,
                )
            )
            active_tasks.add(task)

        wait_timeout = state.poll_interval
        if cooldown_remaining > 0 and not active_tasks:
            wait_timeout = min(wait_timeout, cooldown_remaining)

        if active_tasks:
            done_wait, pending, woke = await _wait_for_tasks_or_wake(
                active_tasks,
                wait_timeout,
            )
            if woke:
                LOGGER.info("wake_sentinel_consumed")
            all_idle = bool(done_wait)
            for task in done_wait:
                try:
                    result = task.result()
                except Exception as exc:
                    LOGGER.warning("dispatch_failed error=%s", exc, exc_info=True)
                    continue
                all_idle = all_idle and not result.dispatched
                LOGGER.info(
                    "dispatch_completed dispatched=%s reason=%s issue_id=%s",
                    str(result.dispatched).lower(),
                    result.reason,
                    result.issue_id or "",
                )
            active_tasks = set(pending)
            if woke:
                continue
            if not active_tasks and all_idle and await _sleep_or_wake(wait_timeout):
                LOGGER.info("wake_sentinel_consumed")
        else:
            if await _sleep_or_wake(wait_timeout):
                LOGGER.info("wake_sentinel_consumed")
