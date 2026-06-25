"""Transient retry marker and classifier helpers."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from redispatch_core import RETRY_MARKER_PREFIX

MAX_OVERLOAD_RETRIES = 2
MAX_TIMEOUT_RETRIES = 1

TRANSIENT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"server_is_overloaded",
        r"service_unavailable",
        r"overloaded",
        r"(?<!\d)(?:429|502|503|504)(?!\d)",
        r"connection reset",
        r"connection error",
        r"rate[._-]?limit",
        # Provider/stream timeouts and process kills surface as exit_code=1 with
        # timed_out=False (observed: Codex SSE header timeout, bare "terminated").
        r"timed out",
        r"timeout",
        r"\bsse\b",
        r"\bterminated\b",
    )
]

_RETRY_MARKER_PATTERN = (
    rf"^{re.escape(RETRY_MARKER_PREFIX)}\s+·\s+(?P<attempt>\d+)\)"
    rf"\s+·\s+(?P<timestamp>\S+)$"
)
RETRY_MARKER_RE = re.compile(_RETRY_MARKER_PATTERN, re.MULTILINE)
RETRY_MARKER_TIMESTAMP_RE = re.compile(_RETRY_MARKER_PATTERN, re.MULTILINE)


def is_transient(stderr: str | None, exit_code: int | None, timed_out: bool) -> bool:
    if timed_out:
        return True
    if not stderr:
        return False
    return any(pattern.search(stderr) for pattern in TRANSIENT_PATTERNS)


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
