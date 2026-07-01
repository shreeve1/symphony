"""Per-binding dispatch state and rate-limit cooldown helpers.

Extracted from ``scheduler.__init__`` as a cohesive leaf: the
``_DispatchState`` value (semaphore cap, in-flight tracking, poll interval,
cooldown bookkeeping) plus the functions that read and mutate its cooldown.
``scheduler.__init__`` re-exports the public names so callers and tests keep
their existing import surface.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from config import ProjectBinding, SymphonyConfig
from plane_adapter import PlaneRateLimitError

LOGGER = logging.getLogger(__name__)

RATE_LIMIT_BASE_COOLDOWN_S = 30.0
RATE_LIMIT_MAX_COOLDOWN_S = 300.0
RATE_LIMIT_JITTER_FRACTION = 0.2


@dataclass
class _DispatchState:
    """Per-binding dispatch state — isolates concurrency from module globals.

    Created by ``run_loop`` for each binding so that semaphore cap, in-flight
    tracking, and poll interval are scoped to one project rather than shared
    across all bindings. Direct ``run_tick`` / ``_dispatch_one`` calls create
    or receive an explicit ``_DispatchState`` so tests and production exercise
    the same state path.

    **Concurrency multiplication:** each binding gets its own semaphore of size
    ``run_cap``, so total host-wide concurrent runs is ``run_cap × num_bindings``.
    Operators must size ``run_cap`` accordingly — the cap is per-project, not
    per-host.

    **Remote-binding cap:** remote coding bindings use per-issue worktrees over
    SSH and can share the normal ``run_cap``. Other remote bindings still run in
    the shared remote checkout, so ``_effective_run_cap`` clamps them to 1.
    """

    semaphore: asyncio.Semaphore
    in_flight_ids: set[str]
    in_flight_lock: asyncio.Lock
    poll_interval: float
    cooldown_until: datetime | None = None
    cooldown_attempts: int = 0
    pending_review_issue_ids: set[str] = field(default_factory=set)
    pending_completion_bodies: dict[str, str] = field(default_factory=dict)
    in_flight_locks: dict[str, frozenset[str]] = field(default_factory=dict)


def _effective_run_cap(config: SymphonyConfig, binding: ProjectBinding | None) -> int:
    """Per-binding concurrency cap.

    Remote coding bindings use per-issue worktrees and can run in parallel;
    other remote bindings still share one checkout and stay serialized.
    """
    if (
        binding is not None
        and binding.is_remote
        and not binding.worktree_default
    ):
        return 1
    return config.run_cap


def _new_dispatch_state(
    config: SymphonyConfig, *, binding: ProjectBinding | None = None
) -> _DispatchState:
    return _DispatchState(
        semaphore=asyncio.Semaphore(_effective_run_cap(config, binding)),
        in_flight_ids=set(),
        in_flight_lock=asyncio.Lock(),
        poll_interval=config.poll_interval_ms / 1000,
    )


def _cooldown_remaining_s(
    state: _DispatchState,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> float:
    if state.cooldown_until is None:
        return 0.0
    remaining = (state.cooldown_until - now()).total_seconds()
    if remaining <= 0:
        state.cooldown_until = None
        return 0.0
    return remaining


def _record_rate_limit(
    state: _DispatchState,
    exc: PlaneRateLimitError,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    jitter: Callable[[], float] = random.random,
) -> None:
    state.cooldown_attempts += 1
    if exc.retry_after_s is not None:
        delay_s = exc.retry_after_s
        delay_s += max(1.0, delay_s * RATE_LIMIT_JITTER_FRACTION) * jitter()
    else:
        delay_s = min(
            RATE_LIMIT_MAX_COOLDOWN_S,
            RATE_LIMIT_BASE_COOLDOWN_S * (2 ** max(0, state.cooldown_attempts - 1)),
        )
        delay_s += delay_s * RATE_LIMIT_JITTER_FRACTION * jitter()
    state.cooldown_until = now() + timedelta(seconds=delay_s)
    LOGGER.warning(
        "plane_rate_limited cooldown_s=%.3f attempts=%s",
        delay_s,
        state.cooldown_attempts,
    )


def _clear_rate_limit(state: _DispatchState) -> None:
    state.cooldown_until = None
    state.cooldown_attempts = 0
