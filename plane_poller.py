"""Compatibility wrapper for the tracker adapter candidate poller."""

from __future__ import annotations

from plane_adapter import (
    CandidateIssue,
    HttpxPlaneTransport,
    PlaneAdapter,
    PlaneContractError,
    PlanePollingAuthError,
    PlanePollingSchemaError,
    build_adapter,
    MAX_MIXED_STATE_PAGES_PER_TICK,
    MAX_PAGES_PER_TICK,
    PAGE_SIZE,
)


async def fetch_todo_issues(adapter: PlaneAdapter) -> list[CandidateIssue]:
    """Fetch dispatchable Todo issues through the tracker adapter seam."""

    return await adapter.list_candidates()


__all__ = [
    "CandidateIssue",
    "HttpxPlaneTransport",
    "MAX_MIXED_STATE_PAGES_PER_TICK",
    "MAX_PAGES_PER_TICK",
    "PAGE_SIZE",
    "PlaneContractError",
    "PlanePollingAuthError",
    "PlanePollingSchemaError",
    "build_adapter",
    "fetch_todo_issues",
]
