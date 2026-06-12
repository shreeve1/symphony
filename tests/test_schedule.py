"""Unit tests for the ``schedule`` module.

Covers plan task 3.9: valid schedule, valid cancellation, missing reason,
naive timestamp, malformed key=value syntax, HTML/entity round-trip,
``not_after < not_before``, identical ``created_at`` tie-breaks, latest
schedule wins, latest cancellation wins, and reschedule after cancellation.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Make the symphony root importable when pytest is run from this directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schedule import (  # noqa: E402  (sys.path manipulation above)
    CANCELLATION_PREFIX,
    CandidateComment,
    SCHEDULE_PREFIX,
    ScheduleEventType,
    ScheduleParseError,
    format_cancellation_comment,
    format_schedule_comment,
    latest_event,
    normalize_comment_body,
    parse_schedule_comment,
)


UTC = timezone.utc


# ---------------------------------------------------------------------------
# Parser: valid schedule
# ---------------------------------------------------------------------------


def test_parse_valid_schedule_with_not_after_and_quoted_reason():
    body = (
        'Symphony-Schedule: not_before=2026-05-08T20:00:00Z '
        'not_after=2026-05-08T22:00:00Z reason="rotate creds"'
    )
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.event_type is ScheduleEventType.SCHEDULE
    assert event.is_schedule
    assert not event.is_cancellation
    assert event.not_before == datetime(2026, 5, 8, 20, 0, tzinfo=UTC)
    assert event.not_after == datetime(2026, 5, 8, 22, 0, tzinfo=UTC)
    assert event.reason == "rotate creds"


def test_parse_schedule_without_not_after_returns_none_for_advisory_field():
    body = 'Symphony-Schedule: not_before=2026-05-08T20:00:00+00:00 reason="rotate creds"'
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.not_after is None
    assert event.not_before == datetime(2026, 5, 8, 20, 0, tzinfo=UTC)


def test_parse_schedule_accepts_offset_other_than_utc_and_normalises_to_utc():
    body = (
        'Symphony-Schedule: not_before=2026-05-08T22:00:00+02:00 reason="ok"'
    )
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.not_before == datetime(2026, 5, 8, 20, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Parser: cancellation
# ---------------------------------------------------------------------------


def test_parse_valid_cancellation():
    body = 'Symphony-Schedule-Cancelled: reason="oncall paged"'
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.is_cancellation
    assert event.reason == "oncall paged"
    assert event.not_before is None
    assert event.not_after is None


def test_cancellation_rejects_unknown_keys():
    body = (
        'Symphony-Schedule-Cancelled: not_before=2026-05-08T20:00:00Z '
        'reason="bad"'
    )
    with pytest.raises(ScheduleParseError):
        parse_schedule_comment(body)


# ---------------------------------------------------------------------------
# Parser: validation failures
# ---------------------------------------------------------------------------


def test_missing_reason_on_schedule_raises():
    with pytest.raises(ScheduleParseError, match="reason"):
        parse_schedule_comment(
            "Symphony-Schedule: not_before=2026-05-08T20:00:00Z"
        )


def test_empty_reason_on_schedule_raises():
    with pytest.raises(ScheduleParseError, match="non-empty"):
        parse_schedule_comment(
            'Symphony-Schedule: not_before=2026-05-08T20:00:00Z reason=""'
        )


def test_missing_reason_on_cancellation_raises():
    with pytest.raises(ScheduleParseError, match="reason"):
        parse_schedule_comment("Symphony-Schedule-Cancelled:")


def test_empty_reason_on_cancellation_raises():
    with pytest.raises(ScheduleParseError, match="non-empty"):
        parse_schedule_comment('Symphony-Schedule-Cancelled: reason=""')


def test_naive_not_before_is_rejected():
    body = 'Symphony-Schedule: not_before=2026-05-08T20:00:00 reason="x"'
    with pytest.raises(ScheduleParseError, match="ISO 8601|UTC offset"):
        parse_schedule_comment(body)


def test_natural_language_not_before_is_rejected():
    body = 'Symphony-Schedule: not_before=tomorrow reason="x"'
    with pytest.raises(ScheduleParseError):
        parse_schedule_comment(body)


def test_malformed_token_raises():
    body = "Symphony-Schedule: not_before== reason=oops"
    with pytest.raises(ScheduleParseError):
        parse_schedule_comment(body)


def test_unknown_keys_on_schedule_raise():
    body = (
        'Symphony-Schedule: not_before=2026-05-08T20:00:00Z '
        'priority=high reason="x"'
    )
    with pytest.raises(ScheduleParseError, match="unknown keys"):
        parse_schedule_comment(body)


def test_duplicate_keys_raise():
    body = (
        'Symphony-Schedule: not_before=2026-05-08T20:00:00Z '
        'not_before=2026-05-08T21:00:00Z reason="x"'
    )
    with pytest.raises(ScheduleParseError, match="duplicate"):
        parse_schedule_comment(body)


def test_not_after_before_not_before_is_rejected():
    body = (
        'Symphony-Schedule: not_before=2026-05-08T22:00:00Z '
        'not_after=2026-05-08T20:00:00Z reason="x"'
    )
    with pytest.raises(ScheduleParseError, match=">= not_before"):
        parse_schedule_comment(body)


def test_malformed_not_after_is_rejected():
    body = (
        'Symphony-Schedule: not_before=2026-05-08T20:00:00Z '
        'not_after=NOTADATE reason="x"'
    )
    with pytest.raises(ScheduleParseError):
        parse_schedule_comment(body)


# ---------------------------------------------------------------------------
# Parser: not-our-comment cases
# ---------------------------------------------------------------------------


def test_unrelated_comment_returns_none():
    assert parse_schedule_comment("just a normal note") is None
    assert parse_schedule_comment(None) is None
    assert parse_schedule_comment("") is None


def test_multiline_comment_finds_first_control_plane_line():
    body = (
        "Some context line.\n"
        'Symphony-Schedule: not_before=2026-05-08T20:00:00Z reason="r"\n'
        "trailing operator commentary"
    )
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.is_schedule


# ---------------------------------------------------------------------------
# HTML / entity round-trip
# ---------------------------------------------------------------------------


def test_html_wrapped_comment_round_trips_with_entities():
    body = (
        '<p>Symphony-Schedule: not_before=2026-05-08T20:00:00Z '
        'reason=&quot;rotate &amp; restart&quot;</p>'
    )
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.reason == "rotate & restart"


def test_normalize_strips_br_and_p_tags():
    s = "<p>Symphony-Schedule:<br/>not_before=2026-05-08T20:00:00Z reason=&quot;x&quot;</p>"
    out = normalize_comment_body(s)
    assert "<p>" not in out
    assert "<br" not in out
    assert "Symphony-Schedule:" in out


def test_html_wrapped_with_br_between_tokens_parses_successfully():
    # Plane often soft-wraps the single control-plane line via <br>; the
    # parser must still see one comment line, not two, so the schedule
    # remains valid.  Regression for round-3 audit finding 1.
    body = (
        "<p>Symphony-Schedule:<br/>not_before=2026-05-08T20:00:00Z "
        "reason=&quot;x&quot;</p>"
    )
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.is_schedule
    assert event.reason == "x"


def test_normalize_preserves_br_inside_quoted_reason():
    # Quote-aware wrapper stripping: <br> between tokens is collapsed to a
    # space, but a literal <br> appearing inside a quoted reason value must
    # round-trip verbatim.  Regression for round-3 audit finding 2.
    body = 'Symphony-Schedule: not_before=2026-05-08T20:00:00Z reason="literal <br> token"'
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.reason == "literal <br> token"


def test_normalize_handles_none_and_collapses_whitespace():
    assert normalize_comment_body(None) == ""
    assert normalize_comment_body("  hello\t\tworld  ") == "hello world"


# ---------------------------------------------------------------------------
# Serialiser
# ---------------------------------------------------------------------------


def test_format_schedule_comment_round_trips_through_parser():
    when = datetime(2026, 5, 8, 20, 0, tzinfo=UTC)
    body = format_schedule_comment(
        not_before=when, reason='rotate "creds"', not_after=when + timedelta(hours=2)
    )
    assert body.startswith(SCHEDULE_PREFIX)
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.is_schedule
    assert event.not_before == when
    assert event.not_after == when + timedelta(hours=2)
    assert event.reason == 'rotate "creds"'


def test_format_schedule_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        format_schedule_comment(
            not_before=datetime(2026, 5, 8, 20, 0), reason="x"
        )


def test_format_schedule_rejects_inverted_window():
    when = datetime(2026, 5, 8, 20, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        format_schedule_comment(
            not_before=when, not_after=when - timedelta(minutes=1), reason="x"
        )


def test_format_cancellation_round_trips():
    body = format_cancellation_comment(reason="oncall paged")
    assert body.startswith(CANCELLATION_PREFIX)
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.is_cancellation
    assert event.reason == "oncall paged"


def test_format_cancellation_rejects_empty_reason():
    with pytest.raises(ValueError):
        format_cancellation_comment(reason="")


# ---------------------------------------------------------------------------
# latest_event: selection rules
# ---------------------------------------------------------------------------


def _schedule_body(when: str, reason: str = "r") -> str:
    return f'{SCHEDULE_PREFIX} not_before={when} reason="{reason}"'


def _cancel_body(reason: str = "stop") -> str:
    return f'{CANCELLATION_PREFIX} reason="{reason}"'


def test_latest_event_returns_none_when_no_control_plane_comments():
    comments = [
        CandidateComment(body="hello", created_at=datetime(2026, 5, 8, 19, 0, tzinfo=UTC)),
        CandidateComment(body="world", created_at=datetime(2026, 5, 8, 20, 0, tzinfo=UTC)),
    ]
    assert latest_event(comments) is None


def test_latest_schedule_wins_over_older_schedule():
    older = CandidateComment(
        body=_schedule_body("2026-05-08T20:00:00Z", "v1"),
        comment_id="a",
        created_at=datetime(2026, 5, 8, 10, 0, tzinfo=UTC),
    )
    newer = CandidateComment(
        body=_schedule_body("2026-05-08T22:00:00Z", "v2"),
        comment_id="b",
        created_at=datetime(2026, 5, 8, 11, 0, tzinfo=UTC),
    )
    event = latest_event([older, newer])
    assert event is not None and event.is_schedule
    assert event.reason == "v2"
    assert event.not_before == datetime(2026, 5, 8, 22, 0, tzinfo=UTC)


def test_latest_cancellation_wins_over_older_schedule():
    older = CandidateComment(
        body=_schedule_body("2026-05-08T20:00:00Z"),
        created_at=datetime(2026, 5, 8, 10, 0, tzinfo=UTC),
    )
    newer = CandidateComment(
        body=_cancel_body("oncall paged"),
        created_at=datetime(2026, 5, 8, 11, 0, tzinfo=UTC),
    )
    event = latest_event([older, newer])
    assert event is not None
    assert event.is_cancellation
    assert event.reason == "oncall paged"


def test_reschedule_after_cancellation():
    cancelled = CandidateComment(
        body=_cancel_body("oncall paged"),
        created_at=datetime(2026, 5, 8, 11, 0, tzinfo=UTC),
    )
    rescheduled = CandidateComment(
        body=_schedule_body("2026-05-08T23:00:00Z", "retry"),
        created_at=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
    )
    event = latest_event([cancelled, rescheduled])
    assert event is not None and event.is_schedule
    assert event.reason == "retry"


def test_identical_created_at_uses_api_order_tiebreak():
    same_ts = datetime(2026, 5, 8, 11, 0, tzinfo=UTC)
    a = CandidateComment(
        body=_schedule_body("2026-05-08T20:00:00Z", "first-api-order"),
        comment_id="a",
        created_at=same_ts,
        api_order=1,
    )
    b = CandidateComment(
        body=_schedule_body("2026-05-08T20:00:00Z", "second-api-order"),
        comment_id="b",
        created_at=same_ts,
        api_order=2,
    )
    event = latest_event([a, b])
    assert event is not None
    assert event.reason == "second-api-order"


def test_identical_created_at_falls_back_to_comment_id_when_no_api_order():
    same_ts = datetime(2026, 5, 8, 11, 0, tzinfo=UTC)
    a = CandidateComment(
        body=_schedule_body("2026-05-08T20:00:00Z", "id-aaa"),
        comment_id="aaa",
        created_at=same_ts,
    )
    b = CandidateComment(
        body=_schedule_body("2026-05-08T20:00:00Z", "id-bbb"),
        comment_id="bbb",
        created_at=same_ts,
    )
    event = latest_event([a, b])
    assert event is not None
    # 'bbb' > 'aaa' so the bbb event wins as the latest.
    assert event.reason == "id-bbb"


def test_identical_created_at_comment_id_tiebreak_independent_of_input_order():
    # Regression: prior _sort_key fell back to the input list index when
    # api_order was absent, so reversing the input list flipped the winner.
    # comment_id must always be the deterministic tie-break.
    same_ts = datetime(2026, 5, 8, 11, 0, tzinfo=UTC)
    bbb_first = CandidateComment(
        body=_schedule_body("2026-05-08T20:00:00Z", "id-bbb"),
        comment_id="bbb",
        created_at=same_ts,
    )
    aaa_second = CandidateComment(
        body=_schedule_body("2026-05-08T20:00:00Z", "id-aaa"),
        comment_id="aaa",
        created_at=same_ts,
    )
    forward = latest_event([aaa_second, bbb_first])
    reversed_order = latest_event([bbb_first, aaa_second])
    assert forward is not None and reversed_order is not None
    # Whichever order the API returns the comments in, the lexicographically
    # greater comment_id ('bbb') must win.
    assert forward.reason == "id-bbb"
    assert reversed_order.reason == "id-bbb"


def test_latest_malformed_event_raises_no_fallback():
    older_valid = CandidateComment(
        body=_schedule_body("2026-05-08T20:00:00Z", "ok"),
        created_at=datetime(2026, 5, 8, 10, 0, tzinfo=UTC),
    )
    latest_malformed = CandidateComment(
        body="Symphony-Schedule: not_before=NOTADATE reason=\"x\"",
        created_at=datetime(2026, 5, 8, 11, 0, tzinfo=UTC),
    )
    with pytest.raises(ScheduleParseError):
        latest_event([older_valid, latest_malformed])


def test_unrelated_comments_in_between_are_ignored():
    schedule = CandidateComment(
        body=_schedule_body("2026-05-08T20:00:00Z", "kept"),
        created_at=datetime(2026, 5, 8, 10, 0, tzinfo=UTC),
    )
    chatter = CandidateComment(
        body="just regular operator commentary",
        created_at=datetime(2026, 5, 8, 11, 0, tzinfo=UTC),
    )
    event = latest_event([schedule, chatter])
    assert event is not None and event.reason == "kept"


# ---------------------------------------------------------------------------
# Round-4 regression tests
# ---------------------------------------------------------------------------


def test_format_round_trips_reason_with_entity_literal():
    # Round-4 audit finding 1: reason text containing the literal characters
    # ``&quot;`` must round-trip through format_schedule_comment ->
    # parse_schedule_comment without entity-decoding inside the quoted span.
    when = datetime(2026, 5, 8, 20, 0, tzinfo=UTC)
    body = format_schedule_comment(
        not_before=when,
        not_after=None,
        reason='literal &quot; token',
    )
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.is_schedule
    assert event.reason == 'literal &quot; token'


def test_normalize_preserves_internal_whitespace_in_quoted_reason():
    # Round-4 audit finding 2: whitespace inside a quoted reason must be
    # preserved verbatim.  The previous implementation collapsed runs of
    # spaces globally, breaking ``reason="a   b"``.
    body = 'Symphony-Schedule: not_before=2026-05-08T20:00:00Z reason="a   b"'
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.reason == "a   b"


def test_html_encoded_outer_quotes_preserve_inner_whitespace():
    # Round-5 audit finding 1: when Plane HTML-encodes the structural
    # quotes around reason, the entity-decoded ``"`` must toggle quote
    # mode so inner whitespace and entities survive verbatim.  Without
    # the fix the inner spaces collapsed to a single space.
    body = '<p>Symphony-Schedule: not_before=2026-05-08T20:00:00Z reason=&quot;a   b&quot;</p>'
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.reason == "a   b"


def test_html_encoded_outer_quotes_with_inner_entity():
    # Companion to the above: confirm an inner ``&amp;`` decodes to ``&``
    # when the outer quotes themselves are HTML-encoded.
    body = (
        "<p>Symphony-Schedule: not_before=2026-05-08T20:00:00Z "
        "reason=&quot;rotate &amp; restart&quot;</p>"
    )
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.reason == "rotate & restart"


def test_unterminated_quoted_value_raises():
    # Round-5 audit finding 2: an unterminated quoted reason must NOT be
    # silently swallowed by the bare-value branch; the parser must raise
    # so callers do not write a corrupted schedule.
    body = 'Symphony-Schedule: not_before=2026-05-08T21:00:00Z reason="unterminated'
    with pytest.raises(ScheduleParseError):
        parse_schedule_comment(body)


def test_unrelated_chatter_does_not_disable_api_order_tiebreak():
    # Round-4 audit finding 3: api_order is the documented tie-break for
    # control-plane events with identical created_at.  Unrelated chatter
    # comments that happen to lack api_order must not flip the winner away
    # from the api_order ordering for the control-plane subset.
    same = datetime(2026, 5, 8, 10, 0, tzinfo=UTC)
    a = CandidateComment(
        body=_schedule_body("2026-05-08T20:00:00Z", "first-api-order"),
        created_at=same,
        comment_id="z",
        api_order=1,
    )
    b = CandidateComment(
        body=_schedule_body("2026-05-08T20:00:00Z", "second-api-order"),
        created_at=same,
        comment_id="a",
        api_order=2,
    )
    chatter = CandidateComment(
        body="unrelated operator note",
        created_at=same,
        comment_id="m",
        api_order=None,
    )
    event = latest_event([a, b, chatter])
    assert event is not None
    # Without the fix the missing api_order on `chatter` disabled api_order
    # for everyone and the comment_id tiebreak picked ``a`` (id 'a' < 'z'),
    # silently overriding the explicit Plane page ordinal on the schedule
    # comments.  With the fix api_order remains active among control-plane
    # candidates and ``b`` (api_order=2) wins.
    assert event.reason == "second-api-order"


# ---------------------------------------------------------------------------
# Round-6 regressions
# ---------------------------------------------------------------------------


def test_format_schedule_comment_rejects_whitespace_only_reason():
    """Plan task 3.6: serializer must reject whitespace-only reason.

    Round-6 audit F1 regression: previously ``_quote_reason`` only checked
    ``if not reason``, accepting ``'   '`` and writing a comment that the
    parser would round-trip back as a non-empty quoted string of spaces.
    The serializer now matches the parser by rejecting any reason whose
    ``.strip()`` is empty.
    """
    when = datetime(2026, 5, 8, 20, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        format_schedule_comment(not_before=when, reason="   ")
    with pytest.raises(ValueError):
        format_cancellation_comment(reason="\t\n  ")


def test_quoted_reason_preserves_inner_whitespace():
    """Round-6 audit F2 regression: round-trip must preserve quoted spaces.

    Previously the parser stripped the quoted reason via ``.strip()``, so
    ``reason="  keep  "`` came back as ``'keep'``.  Quoted reasons must
    round-trip byte-for-byte; only whitespace-only values are rejected.
    """
    when = datetime(2026, 5, 8, 20, 0, tzinfo=UTC)
    body = format_schedule_comment(not_before=when, reason="  keep  ")
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.reason == "  keep  "

    # Cancellation parser uses the same rule.
    body2 = format_cancellation_comment(reason="  keep  ")
    cancel = parse_schedule_comment(body2)
    assert cancel is not None
    assert cancel.is_cancellation
    assert cancel.reason == "  keep  "


def test_html_encoded_outer_quote_with_escaped_html_quote_inside():
    """Round-6 audit F3 regression: ``\\&quot;`` inside ``&quot;..&quot;``.

    When Plane renders a literal ``"`` inside an HTML-encoded quoted reason
    it produces ``\\&quot;``.  The decoded-quote-mode walker must decode
    the escaped entity to ``\\"`` so the tokenizer's ``\\"`` -> ``"``
    rule yields a literal double quote in the parsed reason.
    """
    body = (
        '<p>Symphony-Schedule: not_before=2026-05-08T20:00:00Z '
        'reason=&quot;rotate \\&quot;creds\\&quot;&quot;</p>'
    )
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.reason == 'rotate "creds"'


# ---------------------------------------------------------------------------
# Round-7 regressions
# ---------------------------------------------------------------------------


def test_invalid_quoted_escape_pair_raises() -> None:
    """`\\q` and other unsupported escape pairs in quoted reasons must raise.

    Only `\\"` and `\\\\` are valid. Anything else means the token is malformed
    and the parser must reject the whole comment rather than silently dropping
    the backslash.
    """
    body = (
        'Symphony-Schedule: not_before=2026-05-08T20:00:00Z '
        'reason="bad\\qescape"'
    )
    with pytest.raises(ScheduleParseError):
        parse_schedule_comment(body)


def test_non_iso_datetime_separator_rejected() -> None:
    """A non-`T` separator between date and time must raise.

    `datetime.fromisoformat` is permissive on some Pythons; the strict ISO
    8601 regex gate must catch this before fromisoformat sees it.
    """
    body = (
        'Symphony-Schedule: not_before=2026-05-08X20:00:00Z reason="x"'
    )
    with pytest.raises(ScheduleParseError):
        parse_schedule_comment(body)


def test_bare_value_with_embedded_quote_raises() -> None:
    """A bare value cannot contain `"` anywhere; must raise."""
    body = 'Symphony-Schedule-Cancelled: reason=foo"bar'
    with pytest.raises(ScheduleParseError):
        parse_schedule_comment(body)


# ---------------------------------------------------------------------------
# Round-8 regressions
# ---------------------------------------------------------------------------


def test_format_schedule_comment_rejects_newline_in_reason() -> None:
    """Reason with a newline cannot round-trip (parser is line-oriented)."""
    with pytest.raises(ValueError, match="newline|carriage|line-breaking"):
        format_schedule_comment(
            not_before=datetime(2026, 5, 8, 20, 0, tzinfo=timezone.utc),
            reason="line1\nline2",
        )
    with pytest.raises(ValueError, match="newline|carriage|line-breaking"):
        format_schedule_comment(
            not_before=datetime(2026, 5, 8, 20, 0, tzinfo=timezone.utc),
            reason="line1\rline2",
        )
    with pytest.raises(ValueError, match="newline|carriage|line-breaking"):
        format_cancellation_comment(reason="line1\nline2")


def test_adjacent_tokens_without_whitespace_raise() -> None:
    """`reason="x"not_after=...` must raise; tokens require whitespace separation."""
    body = (
        'Symphony-Schedule: not_before=2026-05-08T20:00:00Z '
        'reason="x"not_after=2026-05-08T21:00:00Z'
    )
    with pytest.raises(ScheduleParseError, match="whitespace"):
        parse_schedule_comment(body)


def test_fractional_seconds_beyond_microseconds_rejected() -> None:
    """7+ digit fractional seconds must raise rather than be silently truncated."""
    body = (
        'Symphony-Schedule: '
        'not_before=2026-05-08T20:00:00.1234567Z '
        'not_after=2026-05-08T20:00:00.1234566Z '
        'reason="x"'
    )
    with pytest.raises(ScheduleParseError, match="ISO 8601"):
        parse_schedule_comment(body)


def test_fractional_seconds_up_to_microseconds_accepted() -> None:
    """6-digit fractional seconds (microseconds) round-trip cleanly."""
    body = (
        'Symphony-Schedule: not_before=2026-05-08T20:00:00.123456Z reason="x"'
    )
    event = parse_schedule_comment(body)
    assert event is not None
    assert event.not_before is not None
    assert event.not_before.microsecond == 123456


# ---------------------------------------------------------------------------
# Round-9 regressions
# ---------------------------------------------------------------------------


def test_format_schedule_comment_rejects_all_line_breaking_chars():
    """``str.splitlines()`` recognises more than \\n and \\r as line breaks;
    any of them in a reason would silently truncate on round-trip because
    parsing is line-oriented.  The serializer must reject every one."""
    not_before = datetime(2026, 5, 8, 20, tzinfo=timezone.utc)
    line_breakers = (
        "\n", "\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029",
    )
    for ch in line_breakers:
        with pytest.raises(ValueError, match="line-breaking"):
            format_schedule_comment(not_before=not_before, reason=f"a{ch}b")
        with pytest.raises(ValueError, match="line-breaking"):
            format_cancellation_comment(reason=f"a{ch}b")


def test_iso_offset_overflow_raises_schedule_parse_error():
    """A datetime at the edge of the representable range with a non-UTC
    offset can raise ``OverflowError`` from ``astimezone(UTC)``.  The
    parser must surface that as a ``ScheduleParseError`` rather than
    leaking the builtin exception."""
    body = 'Symphony-Schedule: not_before=0001-01-01T00:00:00+23:59 reason="x"'
    with pytest.raises(ScheduleParseError, match="out of range"):
        parse_schedule_comment(body)


# ---------------------------------------------------------------------------
# Round-10 regressions
# ---------------------------------------------------------------------------


def test_quoted_datetime_with_surrounding_whitespace_rejected():
    """Quoted datetime values must be ISO 8601 exactly as written.

    Operators must not be able to slip whitespace inside the quotes around
    ``not_before`` / ``not_after`` and have it silently stripped: the value
    `" 2026-05-08T20:00:00Z "` is not ISO 8601 and must raise.
    """
    body = (
        'Symphony-Schedule: '
        'not_before=" 2026-05-08T20:00:00Z " '
        'reason="x"'
    )
    with pytest.raises(ScheduleParseError, match="ISO 8601"):
        parse_schedule_comment(body)

    body_after = (
        'Symphony-Schedule: '
        'not_before=2026-05-08T20:00:00Z '
        'not_after=" 2026-05-08T21:00:00Z " '
        'reason="x"'
    )
    with pytest.raises(ScheduleParseError, match="ISO 8601"):
        parse_schedule_comment(body_after)


def test_whitespace_around_equals_rejected():
    """The grammar is exact ``key=value`` with no whitespace around ``=``.

    Allowing ``key = value`` would invite ambiguity around bare values and
    is not what the serializer emits.  Both schedule and cancellation
    parsers must reject it.
    """
    bad_schedule = (
        'Symphony-Schedule: '
        'not_before = 2026-05-08T20:00:00Z '
        'reason = "x"'
    )
    with pytest.raises(ScheduleParseError):
        parse_schedule_comment(bad_schedule)

    bad_cancel = 'Symphony-Schedule-Cancelled: reason = "x"'
    with pytest.raises(ScheduleParseError):
        parse_schedule_comment(bad_cancel)
