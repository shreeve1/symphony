"""Scheduler shared tracker-port shims.

Small leaf helpers used across every concern module for talking through the
``TrackerAdapter`` port: normalizing sync/async return values (adapters may
return either) and fetching an issue dict. Pure — no dispatch state, no I/O
beyond the adapter, no dependency on ``scheduler.__init__`` — so concern modules
can import these without a cycle.

The six-stub package split did not name a shared-infra seam; these two helpers
are the first occupants. Other leaf shims may join them as later slices extract
more concerns (the selection/tick/loop/reconcile modules all need them).
"""

from __future__ import annotations

import inspect
from typing import Any

from tracker_adapter import TrackerAdapter


async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def fetch_issue(adapter: TrackerAdapter, issue_id: str) -> dict[str, Any]:
    return await adapter.get_issue(issue_id)
