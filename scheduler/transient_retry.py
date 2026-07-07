"""Transient retry marker and classifier helpers."""

from __future__ import annotations

import re

from redispatch_core import (
    MAX_COMBINED_RETRIES as MAX_COMBINED_RETRIES,
    MAX_STALL_RETRIES as MAX_STALL_RETRIES,
    PI_RETRY_TAGS as PI_RETRY_TAGS,
    RETRY_MARKER_PREFIX as RETRY_MARKER_PREFIX,
    RETRY_MARKER_RE as RETRY_MARKER_RE,
    RETRY_MARKER_TIMESTAMP_RE as RETRY_MARKER_TIMESTAMP_RE,
    STALL_MARKER_PREFIX as STALL_MARKER_PREFIX,
    STALL_MARKER_RE as STALL_MARKER_RE,
    STALL_WATCHDOG_SENTINEL as STALL_WATCHDOG_SENTINEL,
    count_all_retries as count_all_retries,
    count_retries as count_retries,
    count_stall_retries as count_stall_retries,
    format_retry_marker as format_retry_marker,
    format_stall_retry_marker as format_stall_retry_marker,
    retry_cooldown_expired as retry_cooldown_expired,
)

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
        r"headers timed out",
        r"rate[._-]?limit",
        # Provider/stream timeouts and process kills surface as exit_code=1 with
        # timed_out=False (observed: Codex SSE header timeout, bare "terminated").
        r"timed out",
        r"timeout",
        r"\bsse\b",
        r"\bterminated\b",
    )
]


def is_transient(stderr: str | None, exit_code: int | None, timed_out: bool) -> bool:
    if timed_out:
        return True
    if not stderr:
        return False
    return any(pattern.search(stderr) for pattern in TRANSIENT_PATTERNS)
