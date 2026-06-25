from __future__ import annotations

from datetime import datetime, timedelta, timezone

from redispatch_core import RETRY_MARKER_PREFIX as REDISPATCH_RETRY_MARKER_PREFIX
from scheduler.transient_retry import (
    MAX_OVERLOAD_RETRIES,
    MAX_TIMEOUT_RETRIES,
    RETRY_MARKER_PREFIX,
    RETRY_MARKER_RE,
    RETRY_MARKER_TIMESTAMP_RE,
    count_retries,
    format_retry_marker,
    is_transient,
    retry_cooldown_expired,
)


def test_is_transient_matches_overload_markers() -> None:
    assert is_transient("server_is_overloaded", 1, False)
    assert is_transient("model overloaded", 1, False)
    assert is_transient("service_unavailable", 1, False)


def test_is_transient_matches_http_and_rate_limit_markers() -> None:
    for stderr in ("HTTP 429", "bad gateway 502", "503", "504", "rate_limit hit"):
        assert is_transient(stderr, 1, False)


def test_is_transient_matches_connection_errors() -> None:
    assert is_transient("connection reset by peer", 1, False)
    assert is_transient("connection error", 1, False)


def test_is_transient_honors_timeout() -> None:
    assert is_transient("", 0, True)


def test_is_transient_rejects_non_transient_failures() -> None:
    traceback = "Traceback (most recent call last):\n  File \"x.py\", line 1\nValueError: bad"
    assert not is_transient(traceback, 1, False)
    assert not is_transient("", 1, False)


def test_retry_marker_format_regex_and_count() -> None:
    now = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
    marker = format_retry_marker(2, "overloaded", now)

    assert marker == "### Symphony Retry (transient · 2) · 2026-06-25T12:00:00+00:00"
    assert RETRY_MARKER_RE.fullmatch(marker)
    match = RETRY_MARKER_TIMESTAMP_RE.fullmatch(marker)
    assert match is not None
    assert match.group("timestamp") == now.isoformat()
    assert count_retries(f"intro\n{marker}\noutro") == 2
    assert count_retries(None) == 0
    assert count_retries("") == 0


def test_retry_cooldown_expired_uses_latest_marker_timestamp() -> None:
    now = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
    old_marker = format_retry_marker(1, "overloaded", now - timedelta(seconds=120))
    latest_marker = format_retry_marker(2, "overloaded", now - timedelta(seconds=30))

    assert not retry_cooldown_expired(f"{latest_marker}\n{old_marker}", now, cooldown_s=60)
    assert retry_cooldown_expired(old_marker, now, cooldown_s=60)


def test_retry_constants_and_redispatch_reexport() -> None:
    assert MAX_OVERLOAD_RETRIES == 2
    assert MAX_TIMEOUT_RETRIES == 1
    assert REDISPATCH_RETRY_MARKER_PREFIX is RETRY_MARKER_PREFIX
