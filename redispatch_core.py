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
STALL_MARKER_PREFIX = "### Symphony Retry (stall"
RETRY_EPOCH_PREFIX = "### Symphony Retry Epoch"
STALL_WATCHDOG_SENTINEL = "SYMPHONY_STALL_WATCHDOG"
# ADR-0034: raised 1→3 — full carrier-persistence budget when no transient
# retry is spent on the same issue (combined ceiling MAX_COMBINED_RETRIES=3
# is the authoritative cap across stall+transient+timeout).
MAX_STALL_RETRIES = 3
MAX_COMBINED_RETRIES = 3

# ADR-0034: pi-retry extension tags — closed allowlist, load-bearing contract.
# The dotfiles pi-retry extension owns these four literals; a rename there
# without updating this set silently regresses carrier-disruption exits to
# block (fail-closed, not silent-loop). If the extension adds a 5th tag,
# update this set in lockstep.
PI_RETRY_TAGS = frozenset(
    {
        "[stall-watchdog-retry]",
        "[rate-limit-retry]",
        "[unknown-error-retry]",
        "[codex-websocket-limit-retry]",
    }
)

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

# Operator move-to-done reland marker pair. DISTINCT from the review
# RELAND pair above: tracker_podium.list_candidates keys review-run
# reselection off RELAND_PENDING_RE specifically, so this distinct prefix
# does NOT trigger review reselection. An operator-done issue redispatches
# as a normal todo implement run; the scheduler consumes this marker after
# the commit run to close the dirty-loop land (finding #2, #3).
OPERATOR_RELAND_PENDING_PREFIX = "### Symphony Operator Reland Pending"
OPERATOR_RELAND_DONE_PREFIX = "### Symphony Operator Reland Done"
OPERATOR_RELAND_PENDING_RE = re.compile(
    rf"^{re.escape(OPERATOR_RELAND_PENDING_PREFIX)}(?:\s|$)", re.MULTILINE
)
OPERATOR_RELAND_DONE_RE = re.compile(
    rf"^{re.escape(OPERATOR_RELAND_DONE_PREFIX)}(?:\s|$)", re.MULTILINE
)
_RETRY_MARKER_PATTERN = (
    rf"^{re.escape(RETRY_MARKER_PREFIX)}\s+·\s+(?P<attempt>\d+)\)"
    rf"\s+·\s+(?P<timestamp>\S+)$"
)
RETRY_MARKER_RE = re.compile(_RETRY_MARKER_PATTERN, re.MULTILINE)
RETRY_MARKER_TIMESTAMP_RE = re.compile(_RETRY_MARKER_PATTERN, re.MULTILINE)
_STALL_MARKER_PATTERN = (
    rf"^{re.escape(STALL_MARKER_PREFIX)}\s+·\s+(?P<attempt>\d+)\)"
    rf"\s+·\s+(?P<timestamp>\S+)$"
)
STALL_MARKER_RE = re.compile(_STALL_MARKER_PATTERN, re.MULTILINE)
_RETRY_EPOCH_PATTERN = (
    rf"^{re.escape(RETRY_EPOCH_PREFIX)} \((?P<reason>[^)\n]+)\)"
    rf" · (?P<timestamp>\S+)$"
)
RETRY_EPOCH_RE = re.compile(_RETRY_EPOCH_PATTERN, re.MULTILINE)


def format_retry_epoch_marker(reason: str, now: datetime) -> str:
    return f"{RETRY_EPOCH_PREFIX} ({reason}) · {now.isoformat()}"


def format_retry_marker(attempt: int, reason: str, now: datetime) -> str:
    return f"{RETRY_MARKER_PREFIX} · {attempt}) · {now.isoformat()}"


def format_stall_retry_marker(attempt: int, now: datetime) -> str:
    return f"{STALL_MARKER_PREFIX} · {attempt}) · {now.isoformat()}"


def _current_retry_epoch(comments_md: str | None) -> str:
    text = comments_md or ""
    matches = list(RETRY_EPOCH_RE.finditer(text))
    return text[matches[-1].end() :] if matches else text


def count_retries(comments_md: str | None) -> int:
    attempts = [
        int(match.group("attempt"))
        for match in RETRY_MARKER_RE.finditer(_current_retry_epoch(comments_md))
    ]
    return max(attempts, default=0)


def count_stall_retries(comments_md: str | None) -> int:
    attempts = [
        int(match.group("attempt"))
        for match in STALL_MARKER_RE.finditer(_current_retry_epoch(comments_md))
    ]
    return max(attempts, default=0)


def count_all_retries(comments_md: str | None) -> int:
    return count_retries(comments_md) + count_stall_retries(comments_md)


def retry_cooldown_expired(
    comments_md: str | None, now: datetime, cooldown_s: int = 60
) -> bool:
    timestamps = [
        datetime.fromisoformat(match.group("timestamp"))
        for match in RETRY_MARKER_TIMESTAMP_RE.finditer(
            _current_retry_epoch(comments_md)
        )
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


def count_operator_reland_pending(comments_md: str | None) -> int:
    """Count outstanding operator move-to-done reland pending markers."""
    if not comments_md:
        return 0
    return len(OPERATOR_RELAND_PENDING_RE.findall(comments_md))


def operator_reland_unconsumed(comments_md: str | None) -> bool:
    """True if an operator-reland pending marker has no balancing done marker.

    pending count > done count, mirroring the reland_unconsumed check in
    tracker_podium.list_candidates but for the distinct operator prefix."""
    if not comments_md:
        return False
    return count_operator_reland_pending(comments_md) > len(
        OPERATOR_RELAND_DONE_RE.findall(comments_md)
    )


def operator_reland_done_body(comments_md: str | None, *, now: datetime) -> str:
    """Emit one OPERATOR_RELAND_DONE line per outstanding pending marker.

    Mirrors scheduler ``_reland_done_body`` so a successful land balances
    every outstanding operator-reland pending marker (prevents re-entry)."""
    if not comments_md:
        return ""
    outstanding = count_operator_reland_pending(comments_md) - len(
        OPERATOR_RELAND_DONE_RE.findall(comments_md)
    )
    if outstanding <= 0:
        return ""
    return "\n".join(
        f"{OPERATOR_RELAND_DONE_PREFIX} · {now.isoformat()}" for _ in range(outstanding)
    )
