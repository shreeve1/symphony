"""Process-neutral commit redispatch helpers.

Keep this module pure so independent processes can share marker vocabulary
without importing each other's scaffolding.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from os import PathLike
from typing import Any

MAX_COMMIT_REDISPATCH = 2
RETRY_MARKER_PREFIX = "### Symphony Retry (transient"
STALL_WATCHDOG_SENTINEL = "SYMPHONY_STALL_WATCHDOG"

# Substring used both as the synthetic operator-reply header and as the marker
# counted to enforce MAX_COMMIT_REDISPATCH. Must keep the `### Operator Reply (`
# shape so prompt_renderer's operator-reply regex surfaces it on resume.
COMMIT_REDISPATCH_REPLY_PREFIX = "### Operator Reply (Symphony auto-commit"

RELAND_PENDING_PREFIX = "### Symphony Reland Pending"
RELAND_DONE_PREFIX = "### Symphony Reland Done"
RELAND_PENDING_RE = re.compile(
    rf"^{re.escape(RELAND_PENDING_PREFIX)}(?:\s|$)", re.MULTILINE
)
RELAND_DONE_RE = re.compile(rf"^{re.escape(RELAND_DONE_PREFIX)}(?:\s|$)", re.MULTILINE)
_RETRY_MARKER_PATTERN = (
    rf"^{re.escape(RETRY_MARKER_PREFIX)}\s+·\s+(?P<attempt>\d+)\)"
    rf"\s+·\s+(?P<timestamp>\S+)$"
)
RETRY_MARKER_RE = re.compile(_RETRY_MARKER_PATTERN, re.MULTILINE)
RETRY_MARKER_TIMESTAMP_RE = re.compile(_RETRY_MARKER_PATTERN, re.MULTILINE)


def format_retry_marker(attempt: int, reason: str, now: datetime) -> str:
    return f"{RETRY_MARKER_PREFIX} · {attempt}) · {now.isoformat()}"


def count_retries(comments_md: str | None) -> int:
    if not comments_md:
        return 0
    attempts = [
        int(match.group("attempt")) for match in RETRY_MARKER_RE.finditer(comments_md)
    ]
    return max(attempts, default=0)


def retry_cooldown_expired(
    comments_md: str | None, now: datetime, cooldown_s: int = 60
) -> bool:
    timestamps = [
        datetime.fromisoformat(match.group("timestamp"))
        for match in RETRY_MARKER_TIMESTAMP_RE.finditer(comments_md or "")
    ]
    if not timestamps:
        return True
    return now - max(timestamps) >= timedelta(seconds=cooldown_s)


def count_commit_redispatches(comments_md: str | None) -> int:
    """Count prior auto-commit re-dispatches recorded in ``comments_md``."""
    if not comments_md:
        return 0
    return comments_md.count(COMMIT_REDISPATCH_REPLY_PREFIX)


def redispatch_commit_note(worktree_path: str | PathLike[Any], branch: str) -> str:
    """Instruction body for a dirty-worktree commit re-dispatch note."""
    return (
        f"Your worktree at `{worktree_path}` (branch `{branch}`) has uncommitted "
        f"changes, but the Issue was marked done with nothing committed — so "
        f"the work cannot be landed and would be lost.\n\n"
        f"Commit only the work that already exists in the worktree: run the "
        f"repo's tests for the changed code, then `git add -A && git commit` "
        f"with a clear message. Do not start new work or expand scope. When the "
        f"commit lands, end your turn."
    )
