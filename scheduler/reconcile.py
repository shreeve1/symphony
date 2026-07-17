"""Scheduler reconcile concern module.

The reconcile functions previously lived inline in scheduler/__init__.py.
They are extracted here for seam isolation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from config import ProjectBinding, SymphonyConfig
from notifier import TelegramNotifier
from plane_adapter import PlaneRateLimitError
from tracker_adapter import TrackerAdapter
from tracker_contract import TrackerRole
from tracker_types import CommentPayload, _is_state

from .bindings import binding_from_config
from .dispatch_state import _DispatchState
from .ports import fetch_issue, maybe_await

LOGGER = logging.getLogger(__name__)


async def reconcile_pending_review(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    dispatch_state: _DispatchState,
    *,
    notifier: TelegramNotifier | None = None,
) -> int:
    """Retry post-agent review transition after Plane rate-limit interruption."""

    if not dispatch_state.pending_review_issue_ids:
        return 0

    async with dispatch_state.in_flight_lock:
        in_flight_ids = set(dispatch_state.in_flight_ids)

    reconciled = 0
    for issue_id in tuple(dispatch_state.pending_review_issue_ids):
        if issue_id in in_flight_ids:
            continue
        issue = await fetch_issue(adapter, issue_id)
        if not _is_state(
            issue,
            adapter.contract.state_name_for_role(TrackerRole.STATE_RUNNING),
            adapter.contract.state_value_for_role(TrackerRole.STATE_RUNNING),
        ):
            dispatch_state.pending_review_issue_ids.discard(issue_id)
            dispatch_state.pending_completion_bodies.pop(issue_id, None)
            continue
        issue_identifier = str(
            issue.get("sequence_id") or issue.get("identifier") or issue_id
        )
        comment_body = dispatch_state.pending_completion_bodies.get(issue_id)
        if comment_body:
            try:
                await adapter.add_comment(issue_id, CommentPayload(body=comment_body))
                dispatch_state.pending_completion_bodies.pop(issue_id, None)
            except PlaneRateLimitError:
                raise
        await adapter.transition_state(issue_id, TrackerRole.STATE_IN_REVIEW)
        LOGGER.info(
            "pending_review_reconciled issue_id=%s identifier=%s",
            issue_id,
            issue_identifier,
        )
        dispatch_state.pending_review_issue_ids.discard(issue_id)
        reconciled += 1
    return reconciled


async def reconcile_orphaned_runs(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    binding: ProjectBinding | None = None,
) -> int:
    """Reap durable Podium Run rows orphaned by scheduler restart."""

    reconcile = getattr(adapter, "reconcile_orphaned_runs", None)
    if not callable(reconcile):
        return 0
    timestamp = now().isoformat()
    resolved_binding = binding or binding_from_config(config)
    binding_name = resolved_binding.name if resolved_binding is not None else ""
    LOGGER.info("run_reconcile_begin binding=%s", binding_name)
    reaped = int(await maybe_await(reconcile(reaped_at=timestamp)))
    LOGGER.info("run_reconcile_done binding=%s reaped=%d", binding_name, reaped)
    return reaped


async def patrol_run_retention(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    *,
    binding: ProjectBinding | None = None,
) -> int:
    """Prune patrol Run rows/logs to cap per issue."""

    prune = getattr(adapter, "prune_patrol_runs", None)
    if not callable(prune):
        return 0
    resolved_binding = binding or binding_from_config(config)
    binding_name = resolved_binding.name if resolved_binding is not None else ""
    LOGGER.info("patrol_run_retention_begin binding=%s", binding_name)
    counts = await maybe_await(prune())
    pruned_rows = int(counts.get("pruned_rows", 0))
    pruned_logs = int(counts.get("pruned_logs", 0))
    LOGGER.info(
        "patrol_run_retention_done binding=%s pruned_rows=%d pruned_logs=%d",
        binding_name,
        pruned_rows,
        pruned_logs,
    )
    return pruned_rows + pruned_logs


async def run_log_retention(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    binding: ProjectBinding | None = None,
) -> int:
    """Prune old Podium Run log files while keeping durable Run rows."""

    prune = getattr(adapter, "prune_run_logs", None)
    if not callable(prune):
        return 0
    resolved_binding = binding or binding_from_config(config)
    binding_name = resolved_binding.name if resolved_binding is not None else ""
    now_dt = now()
    LOGGER.info("log_retention_begin binding=%s", binding_name)
    pruned = int(await maybe_await(prune(now=now_dt)))
    LOGGER.info("log_retention_done binding=%s pruned=%d", binding_name, pruned)
    return pruned


async def reconcile_stale_running(
    adapter: TrackerAdapter,
    run_timeout_ms: int,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    notifier: TelegramNotifier | None = None,
    dispatch_state: _DispatchState | None = None,
) -> None:
    """Reconcile Running issues whose durable claim comment is stale or interrupted."""

    in_flight_ids: set[str] = set()
    if dispatch_state is not None:
        async with dispatch_state.in_flight_lock:
            in_flight_ids = set(dispatch_state.in_flight_ids)

    interrupted_grace = timedelta(seconds=60)
    timeout_delta = timedelta(milliseconds=run_timeout_ms)
    for issue in await adapter.list_issues_by_state(
        TrackerRole.STATE_RUNNING,
        per_page=SCHEDULED_RELEASE_PAGE_SIZE,
        max_pages=SCHEDULED_RELEASE_MAX_PAGES_PER_TICK,
    ):
        issue_id = str(issue["id"])
        claim_time = await _claimed_at(adapter, issue_id)
        if claim_time is None:
            # No Run row and no claim comment: the issue was flipped to
            # `running` outside the scheduler's claim path (#252 wedge — e.g.
            # a patrol/monitor write bypassed the claim). Recover it to `todo`
            # so the scheduler re-dispatches, unless THIS scheduler is
            # mid-claim. Re-check in_flight freshly under the lock right before
            # the flip (NOT the entry snapshot): a concurrent _dispatch_one can
            # reserve + transition an issue to running after our snapshot, and
            # an issue is always added to in_flight BEFORE transition_state(
            # running), so a flip-time check always sees a mid-claim issue and
            # skips it.
            if dispatch_state is not None:
                async with dispatch_state.in_flight_lock:
                    if issue_id in dispatch_state.in_flight_ids:
                        continue
            await adapter.transition_state(issue_id, TrackerRole.STATE_TODO)
            LOGGER.info(
                "state_transitioned issue_id=%s state=todo reason=unclaimed-running",
                issue_id,
            )
            continue
        elapsed = now() - claim_time
        issue_name = str(issue.get("name", ""))
        issue_identifier = str(
            issue.get("sequence_id") or issue.get("identifier") or issue_id
        )
        if elapsed > timeout_delta:
            await _block_issue(
                adapter,
                issue_id,
                "Symphony claim timed out after scheduler restart",
                issue_name=issue_name,
                issue_identifier=issue_identifier,
                notifier=notifier,
            )
            continue
        if issue_id not in in_flight_ids and elapsed > interrupted_grace:
            await adapter.transition_state(issue_id, TrackerRole.STATE_IN_REVIEW)
            LOGGER.info(
                "state_transitioned issue_id=%s state=in-review reason=stale-running",
                issue_id,
            )


async def reconcile_startup(
    config: SymphonyConfig,
    adapter: TrackerAdapter,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    notifier: TelegramNotifier | None = None,
    binding: ProjectBinding | None = None,
) -> int:
    """Reconcile startup state: recover Plane issues stuck in Running,
    prune patrol Run rows/logs.

    Returns the number of items cleaned up. Runs before the main tick loop so
    the scheduler starts clean after a restart.
    """
    cleaned = 0

    cleaned += await reconcile_orphaned_runs(config, adapter, now=now, binding=binding)
    await run_log_retention(config, adapter, now=now, binding=binding)
    await patrol_run_retention(config, adapter, binding=binding)

    stale_running_issues: list[dict[str, Any]] = []
    for issue in await adapter.list_issues_by_state(
        TrackerRole.STATE_RUNNING,
        per_page=SCHEDULED_RELEASE_PAGE_SIZE,
        max_pages=SCHEDULED_RELEASE_MAX_PAGES_PER_TICK,
    ):
        issue_id = str(issue["id"])
        identifier = str(
            issue.get("sequence_id") or issue.get("identifier") or issue_id
        )
        claim_time = await _claimed_at(adapter, issue_id)
        if claim_time is not None and (now() - claim_time) <= timedelta(
            milliseconds=config.run_timeout_ms
        ):
            continue
        stale_running_issues.append(
            {
                "id": issue_id,
                "identifier": identifier,
                "name": issue.get("name", ""),
                "claim_time": claim_time,
            }
        )

    for issue in stale_running_issues:
        issue_url, dashboard_url = _build_urls(config, issue["id"])
        if issue["claim_time"] is None:
            message = "Symphony claim missing after scheduler restart"
        else:
            elapsed_ms = int((now() - issue["claim_time"]).total_seconds() * 1000)
            message = (
                f"Symphony claim timed out after scheduler restart "
                f"(claimed {elapsed_ms}ms ago, timeout={config.run_timeout_ms}ms)"
            )
        await _block_issue(
            adapter,
            issue["id"],
            message,
            issue_name=str(issue["name"]),
            issue_identifier=issue["identifier"],
            notifier=notifier,
            issue_url=issue_url,
            dashboard_url=dashboard_url,
        )
        cleaned += 1
        LOGGER.info(
            "reconcile_startup_reaped_issue issue_id=%s",
            issue["id"],
        )

    LOGGER.info("reconcile_startup_completed cleaned=%d", cleaned)
    return cleaned


# Symbols resolved from the parent package at import time (circular-import safe
# because __init__ imports .reconcile at the bottom, after all definitions).
from . import (  # noqa: E402
    SCHEDULED_RELEASE_MAX_PAGES_PER_TICK,
    SCHEDULED_RELEASE_PAGE_SIZE,
    _block_issue,
    _build_urls,
    _claimed_at,
)
