"""Symphony ticket schedule parsing.

This module owns the *one-shot* schedule contract layered on top of Plane via
two append-only comment shapes plus the ``scheduled`` label::

    Symphony-Schedule: not_before=<iso8601> [not_after=<iso8601>] reason="..."
    Symphony-Schedule-Cancelled: reason="..."

Hard invariants (see ``plans/symphony-ticket-scheduling.md``):

* ``not_before`` MUST be ISO 8601 with an explicit UTC offset or trailing ``Z``.
  Naive datetimes and natural language are rejected.
* ``reason`` is required and non-empty for both schedule and cancellation
  events.
* ``not_after`` is advisory only.  When present it must parse and must not be
  earlier than ``not_before``.
* The latest valid schedule or cancellation event wins.  Comments are sorted by
  ``created_at`` with a deterministic tiebreaker on Plane comment ID / API
  order so reschedules and races are stable.
* No fallback to older schedules when the latest event is malformed; that case
  is the caller's responsibility to handle (block + parse-error audit).

This module is pure: parsing only, no I/O.  Callers fetch comments via the
Plane adapter and pass them in.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Optional, Sequence


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class ScheduleEventType(str, Enum):
    """Kind of schedule control-plane event found on a Plane ticket."""

    SCHEDULE = "schedule"
    CANCELLATION = "cancellation"


class ScheduleParseError(ValueError):
    """Raised when a candidate schedule comment is structurally invalid.

    Callers should treat ScheduleParseError on the *latest* event as a
    blocking condition and write a parse-error audit comment; older valid
    events are NOT used as a fallback (see plan task 7.2).
    """


@dataclass(frozen=True)
class ScheduleEvent:
    """Immutable record of a single parsed schedule control-plane event.

    Attributes:
        event_type:    schedule or cancellation.
        not_before:    Required for SCHEDULE events; always None for
                       CANCELLATION.  Always timezone-aware UTC.
        not_after:     Optional advisory upper bound for SCHEDULE; always None
                       for CANCELLATION.  Always timezone-aware UTC when set.
        reason:        Required, non-empty, stripped operator-supplied reason.
        comment_id:    Plane comment UUID/string used as deterministic
                       secondary sort key.  May be None when caller has no
                       stable id.
        comment_created_at: Comment creation time used as primary sort key.
                       May be None when the caller cannot supply it; in that
                       case latest-event-wins falls back to API/order.
        raw_comment:   Original (possibly HTML) comment body the event was
                       parsed from, retained for audit trails.
    """

    event_type: ScheduleEventType
    reason: str
    not_before: Optional[datetime] = None
    not_after: Optional[datetime] = None
    comment_id: Optional[str] = None
    comment_created_at: Optional[datetime] = None
    raw_comment: Optional[str] = None

    @property
    def is_schedule(self) -> bool:
        return self.event_type is ScheduleEventType.SCHEDULE

    @property
    def is_cancellation(self) -> bool:
        return self.event_type is ScheduleEventType.CANCELLATION


# ---------------------------------------------------------------------------
# Comment shape constants
# ---------------------------------------------------------------------------


SCHEDULE_PREFIX = "Symphony-Schedule:"
CANCELLATION_PREFIX = "Symphony-Schedule-Cancelled:"

# Recognized key=value tokens.  Order in the comment is not significant; the
# parser tokenises after stripping HTML.
_VALID_SCHEDULE_KEYS = frozenset({"not_before", "not_after", "reason"})
_VALID_CANCELLATION_KEYS = frozenset({"reason"})

# Tokeniser:
#   key="quoted value with spaces"
#   key=bare-value-without-spaces
# We deliberately accept only these two forms so reason values must always be
# quoted when they contain whitespace, eliminating ambiguity.
_TOKEN_RE = re.compile(
    r"""
    (?P<key>[A-Za-z_][A-Za-z0-9_]*)
    =
    (?:
        "(?P<qval>(?:[^"\\]|\\["\\])*)"
      | (?P<bval>[^"\s][^"\s]*)
    )
    """,
    re.VERBOSE,
)


# ---------------------------------------------------------------------------
# HTML normalisation
# ---------------------------------------------------------------------------


_BR_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_CLOSE_P_RE = re.compile(r"</\s*p\s*>", re.IGNORECASE)
_OPEN_P_RE = re.compile(r"<\s*p(?:\s+[^>]*)?>", re.IGNORECASE)
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_HORIZ_WS = " \t\r\f\v"


def _decode_entity_at(s: str, i: int) -> tuple[str, int] | None:
    j = s.find(";", i + 1, i + 16)
    if j == -1:
        return None
    literal = s[i : j + 1]
    decoded = html.unescape(literal)
    if decoded == literal:
        return None
    return decoded, j + 1


def _normalize_outside_quotes(s: str) -> str:
    """Strip wrappers, decode entities, and collapse whitespace — quote-aware.

    The Symphony control-plane format encloses the ``reason`` value in
    double quotes and supports ``\\"`` and ``\\\\`` escapes inside.  Anything
    between an unescaped opening ``"`` and the matching closing ``"`` MUST be
    preserved byte-for-byte until :func:`_tokenise` performs explicit
    unescaping; if we collapsed whitespace, decoded entities, or stripped
    HTML wrappers inside that span we would silently corrupt valid reasons
    such as ``reason="a   b"``, ``reason="literal &quot; token"``, or
    ``reason="literal <br> token"``.

    The walker performs three normalisations OUTSIDE quoted spans only:

    1. Plane wrapper tags ``<br>``/``<br/>``/``<p ...>``/``</p>`` are replaced
       with a single space.  We use a space (not a newline) because Plane
       emits ``<br>`` to soft-wrap a single logical comment line, and the
       parser only inspects the first prefix-bearing line — splitting would
       hide the rest of the payload.
    2. HTML entities are decoded via :func:`html.unescape`.  Plane encodes
       ``"`` as ``&quot;`` in its rich-text payload, so we must decode here
       to recover the structural quote characters.
    3. Runs of horizontal whitespace collapse to a single space.

    Inside quoted spans every character is copied verbatim, including the
    two-character escape sequences ``\\X`` (so ``\\"`` does not prematurely
    end the quote and entity literals such as ``&quot;`` round-trip).
    """
    n = len(s)
    out: list[str] = []
    i = 0
    in_quote = False
    # When a quoted span is opened by a *decoded* HTML entity (``&quot;``)
    # rather than a literal ``"`` we are still in HTML-decoding mode and
    # must continue to decode entities inside the span.  Plane uses
    # ``reason=&quot;rotate &amp; restart&quot;`` for rich-text payloads, so
    # the inner ``&amp;`` must become ``&``.  When the opening quote is a
    # real ``"`` (operator typed plain text) we treat the inside as opaque
    # and a literal ``&quot;`` survives verbatim.
    quote_decoded = False
    pending_ws = False  # collapse runs of horizontal whitespace outside quotes

    def emit_pending_ws() -> None:
        nonlocal pending_ws
        if pending_ws:
            out.append(" ")
            pending_ws = False

    def emit_outside_char(c: str, *, decoded: bool = False) -> None:
        # Emit a single character that originated outside any quoted span.
        # ``decoded`` flags a character that came from html.unescape; when
        # the character is ``"`` it opens a quoted span that is still in
        # decoding mode, so subsequent entity literals inside continue to
        # be decoded (Plane rich-text encodes both the structural quote
        # and inner entities using ``&quot;``/``&amp;`` etc.).
        nonlocal in_quote, quote_decoded
        if c == '"':
            emit_pending_ws()
            in_quote = True
            quote_decoded = decoded
            out.append(c)
            return
        emit_pending_ws()
        out.append(c)

    while i < n:
        ch = s[i]
        if in_quote:
            # Inside a quote opened by a *literal* ``"``: copy verbatim,
            # respect ``\X`` escapes, never touch entities or whitespace.
            if not quote_decoded:
                if ch == "\\" and i + 1 < n:
                    out.append(ch)
                    out.append(s[i + 1])
                    i += 2
                    continue
                if ch == '"':
                    in_quote = False
                out.append(ch)
                i += 1
                continue
            # Inside a quote opened by a *decoded* entity: continue to
            # decode entities and respect ``\X`` escapes; whitespace and
            # wrapper tags are left untouched (no collapse, no strip) so
            # the content of the quoted reason still round-trips byte for
            # byte once tokenisation strips the bracketing quotes.
            if ch == "\\" and i + 1 < n:
                nxt = s[i + 1]
                # If the byte after the backslash is the start of an HTML
                # entity (``\&quot;``) we must decode the entity first so
                # tokenisation later sees ``\"`` (a real escaped quote) and
                # not the still-encoded literal ``\&quot;``.  This mirrors
                # the bare-entity branch below.
                if nxt == "&":
                    decoded_entity = _decode_entity_at(s, i + 1)
                    if decoded_entity is not None:
                        decoded, next_i = decoded_entity
                        out.append("\\")
                        for dch in decoded:
                            # A decoded ``"`` closes the span only if
                            # the backslash didn't escape it.  Since
                            # we *did* escape it, copy verbatim.
                            out.append(dch)
                        i = next_i
                        continue
                out.append(ch)
                out.append(nxt)
                i += 2
                continue
            if ch == '"':
                in_quote = False
                quote_decoded = False
                out.append(ch)
                i += 1
                continue
            if ch == "&":
                decoded_entity = _decode_entity_at(s, i)
                if decoded_entity is None:
                    out.append(ch)
                    i += 1
                else:
                    decoded, next_i = decoded_entity
                    for dch in decoded:
                        if dch == '"':
                            # Closing entity-encoded quote.
                            in_quote = False
                            quote_decoded = False
                            out.append(dch)
                        else:
                            out.append(dch)
                            if not in_quote:
                                # Opening of a new outer span; rare
                                # but treat the next decoded chars as
                                # outside until another quote arrives.
                                pass
                    i = next_i
                continue
            out.append(ch)
            i += 1
            continue

        # ----- outside quotes -----
        if ch == '"':
            emit_outside_char(ch)
            i += 1
            continue

        if ch == "<":
            matched = False
            for pattern in (_BR_RE, _CLOSE_P_RE, _OPEN_P_RE):
                m = pattern.match(s, i)
                if m is not None:
                    pending_ws = True  # treat wrapper as whitespace
                    i = m.end()
                    matched = True
                    break
            if not matched:
                emit_outside_char(ch)
                i += 1
            continue

        if ch in _HORIZ_WS or ch == "\n":
            # Preserve real newlines; collapse other horizontal whitespace.
            if ch == "\n":
                pending_ws = False  # newline supersedes pending space
                out.append("\n")
            else:
                pending_ws = True
            i += 1
            continue

        # Entity-aware decode: when an HTML entity sits OUTSIDE quotes we
        # decode it via html.unescape and then feed each decoded character
        # back through the outside-quote path.  This is critical when the
        # entity decodes to ``"`` (e.g. ``&quot;``): Plane HTML uses the
        # entity-encoded form for structural quotes, and only by toggling
        # ``in_quote`` on the decoded ``"`` do we keep the inside of the
        # quoted span untouched (whitespace, wrappers, and other entity
        # literals all survive verbatim).
        if ch == "&":
            decoded_entity = _decode_entity_at(s, i)
            if decoded_entity is None:
                # Not a recognised entity — keep the raw text.
                emit_outside_char(ch)
                i += 1
            else:
                decoded, next_i = decoded_entity
                for dch in decoded:
                    if in_quote:
                        # Within a decoded-quote span the inner chars
                        # are still being decoded; emit verbatim and
                        # close on a structural quote.
                        if dch == '"':
                            in_quote = False
                            quote_decoded = False
                        out.append(dch)
                    else:
                        emit_outside_char(dch, decoded=True)
                i = next_i
            continue

        emit_outside_char(ch)
        i += 1

    result = "".join(out)
    # Per-line strip: remove leading/trailing whitespace on each line and
    # drop blank lines, matching the previous public behaviour.
    lines = [line.strip(_HORIZ_WS) for line in result.splitlines()]
    return "\n".join(line for line in lines if line)


def normalize_comment_body(body: object) -> str:
    """Strip simple HTML wrappers and decode entities from a Plane comment.

    Plane returns ``comment_html`` (with ``<p>``/``<br>`` and entity-encoded
    quotes) for stdout-style comments while ``comment_stripped`` is plain.
    Callers may pass either; we normalise to plain-text by handling only the
    block wrappers Plane actually produces (``<p>``, ``<br>``), decoding
    HTML entities, collapsing horizontal whitespace, and stripping the result.

    All three normalisations (wrapper stripping, entity decoding, whitespace
    collapsing) are **quote-aware** — they apply only outside double-quoted
    spans.  Inside quoted ``reason="..."`` values everything is preserved
    byte-for-byte until :func:`_tokenise` performs the explicit ``\\"``/``\\\\``
    unescaping.  This guarantees round-trip stability for reasons that
    contain literal ``<br>``, multiple consecutive spaces, or HTML entity
    text such as ``&quot;``.

    Comments containing raw HTML other than the recognised Plane wrappers
    are left as-is so the parser will reject them rather than silently drop
    content.
    """
    if body is None:
        return ""
    return _normalize_outside_quotes(str(body))


# ---------------------------------------------------------------------------
# Datetime parsing
# ---------------------------------------------------------------------------


_ISO_8601_STRICT_RE = re.compile(
    r"""
    \A
    \d{4}-\d{2}-\d{2}            # date
    T                             # required ISO 'T' separator
    \d{2}:\d{2}:\d{2}            # time
    (?:\.\d{1,6})?                # optional fractional seconds (cap at 6 digits;
                                  # higher precision than microsecond would be
                                  # silently truncated by datetime, which can
                                  # let not_after < not_before slip through)
    (?:Z|[+-]\d{2}:\d{2})        # required UTC offset or 'Z'
    \Z
    """,
    re.VERBOSE,
)


def _parse_iso_utc(value: str, *, field: str) -> datetime:
    """Parse an ISO 8601 string requiring an explicit UTC offset or ``Z``.

    Gated by a strict ISO 8601 regex so that ``datetime.fromisoformat``'s
    permissive behaviour (e.g. accepting non-ISO separators in some Python
    builds) cannot leak through.  Returns a timezone-aware UTC datetime.
    Naive datetimes (no offset) and natural-language strings are rejected
    with ScheduleParseError.
    """
    # Do NOT strip: surrounding whitespace inside a quoted datetime value
    # ("\\ 2026-...Z \\") means the supplied value is not ISO 8601 and must be
    # rejected.  Quoted token values are returned verbatim by the tokeniser.
    raw = value
    if not raw:
        raise ScheduleParseError(f"{field} is empty")
    if not _ISO_8601_STRICT_RE.match(raw):
        raise ScheduleParseError(f"{field} is not a valid ISO 8601 datetime: {raw!r}")
    # datetime.fromisoformat in Python 3.11+ accepts the trailing 'Z'.  Be
    # defensive for older runtimes anyway.
    candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ScheduleParseError(
            f"{field} is not a valid ISO 8601 datetime: {raw!r}"
        ) from exc
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise ScheduleParseError(
            f"{field} must include an explicit UTC offset or 'Z'; got {raw!r}"
        )
    # ``astimezone(UTC)`` can raise OverflowError when the offset shift
    # would push the datetime out of the representable range
    # (e.g. year 0001 with a positive offset).  Surface that as a
    # ScheduleParseError so callers don't see a leaked builtin.
    try:
        return parsed.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise ScheduleParseError(
            f"{field} is out of range when normalised to UTC: {raw!r}"
        ) from exc


# ---------------------------------------------------------------------------
# Single-event parser
# ---------------------------------------------------------------------------


def _tokenise(payload: str) -> dict[str, str]:
    """Tokenise the key=value payload following the prefix.

    Returns a ``dict`` with the discovered keys.  Raises ``ScheduleParseError``
    on duplicate keys or unrecognised trailing junk.
    """
    tokens: dict[str, str] = {}
    cursor = 0
    payload = payload.strip()
    while cursor < len(payload):
        match = _TOKEN_RE.match(payload, cursor)
        if not match:
            # Permit leading/trailing whitespace between tokens.
            if payload[cursor].isspace():
                cursor += 1
                continue
            raise ScheduleParseError(
                f"unparseable token at offset {cursor} in {payload!r}"
            )
        key = match.group("key")
        qval = match.group("qval")
        bval = match.group("bval")
        if key in tokens:
            raise ScheduleParseError(f"duplicate key {key!r}")
        if qval is not None:
            # Unescape only the two valid escape pairs: \" and \\.
            tokens[key] = re.sub(r'\\(["\\])', r"\1", qval)
        else:
            tokens[key] = bval
        cursor = match.end()
        # Require at least one whitespace character (or EOF) between tokens.
        # Without this, ``reason="x"not_after=...`` would silently parse as
        # two adjacent tokens with no separator.
        if cursor < len(payload):
            if not payload[cursor].isspace():
                raise ScheduleParseError(
                    f"missing whitespace between tokens at offset {cursor} in {payload!r}"
                )
            while cursor < len(payload) and payload[cursor].isspace():
                cursor += 1
    return tokens


def parse_schedule_comment(
    body: object,
    *,
    comment_id: Optional[str] = None,
    comment_created_at: Optional[datetime] = None,
) -> Optional[ScheduleEvent]:
    """Parse a single comment body, returning ``ScheduleEvent`` or ``None``.

    Returns ``None`` when the comment is not a schedule control-plane comment
    at all (no recognised prefix on any line).  Raises
    ``ScheduleParseError`` when a recognised prefix is present but the rest
    of the line does not validate; callers MUST treat this as a hard failure
    on the latest event and not silently fall back.
    """
    text = normalize_comment_body(body)
    if not text:
        return None

    # The control-plane comment is single-line by convention.  We scan lines
    # for the first one starting with a known prefix, so trailing operator
    # commentary on subsequent lines is tolerated and ignored.
    line: Optional[str] = None
    prefix: Optional[str] = None
    for candidate in text.splitlines():
        stripped = candidate.lstrip()
        if stripped.startswith(SCHEDULE_PREFIX):
            line = stripped
            prefix = SCHEDULE_PREFIX
            break
        if stripped.startswith(CANCELLATION_PREFIX):
            line = stripped
            prefix = CANCELLATION_PREFIX
            break
    if line is None or prefix is None:
        return None

    payload = line[len(prefix) :].strip()
    tokens = _tokenise(payload)

    if prefix == SCHEDULE_PREFIX:
        return _build_schedule_event(
            tokens,
            comment_id=comment_id,
            comment_created_at=comment_created_at,
            raw_comment=str(body) if body is not None else None,
        )
    return _build_cancellation_event(
        tokens,
        comment_id=comment_id,
        comment_created_at=comment_created_at,
        raw_comment=str(body) if body is not None else None,
    )


def _build_schedule_event(
    tokens: dict[str, str],
    *,
    comment_id: Optional[str],
    comment_created_at: Optional[datetime],
    raw_comment: Optional[str],
) -> ScheduleEvent:
    extras = set(tokens) - _VALID_SCHEDULE_KEYS
    if extras:
        raise ScheduleParseError(
            f"unknown keys for Symphony-Schedule: {sorted(extras)!r}"
        )
    if "not_before" not in tokens:
        raise ScheduleParseError("Symphony-Schedule missing required not_before")
    if "reason" not in tokens:
        raise ScheduleParseError("Symphony-Schedule missing required reason")

    # Preserve the reason verbatim (including any leading/trailing
    # whitespace operators chose to include) so it round-trips through the
    # serialiser.  Reject only when the reason has no non-blank content.
    reason = tokens["reason"]
    if not reason.strip():
        raise ScheduleParseError("Symphony-Schedule reason must be non-empty")

    not_before = _parse_iso_utc(tokens["not_before"], field="not_before")
    not_after: Optional[datetime] = None
    if "not_after" in tokens:
        not_after = _parse_iso_utc(tokens["not_after"], field="not_after")
        if not_after < not_before:
            raise ScheduleParseError(
                "Symphony-Schedule not_after must be >= not_before"
            )

    return ScheduleEvent(
        event_type=ScheduleEventType.SCHEDULE,
        reason=reason,
        not_before=not_before,
        not_after=not_after,
        comment_id=comment_id,
        comment_created_at=comment_created_at,
        raw_comment=raw_comment,
    )


def _build_cancellation_event(
    tokens: dict[str, str],
    *,
    comment_id: Optional[str],
    comment_created_at: Optional[datetime],
    raw_comment: Optional[str],
) -> ScheduleEvent:
    extras = set(tokens) - _VALID_CANCELLATION_KEYS
    if extras:
        raise ScheduleParseError(
            f"unknown keys for Symphony-Schedule-Cancelled: {sorted(extras)!r}"
        )
    if "reason" not in tokens:
        raise ScheduleParseError("Symphony-Schedule-Cancelled missing required reason")
    # Preserve verbatim; reject only when reason is whitespace-only.
    reason = tokens["reason"]
    if not reason.strip():
        raise ScheduleParseError("Symphony-Schedule-Cancelled reason must be non-empty")
    return ScheduleEvent(
        event_type=ScheduleEventType.CANCELLATION,
        reason=reason,
        comment_id=comment_id,
        comment_created_at=comment_created_at,
        raw_comment=raw_comment,
    )


# ---------------------------------------------------------------------------
# Serialiser (used by CLI to author comments)
# ---------------------------------------------------------------------------


def _quote_reason(reason: str) -> str:
    # Reject whitespace-only reasons in addition to empty ones; this
    # matches the parser, which rejects ``reason="   "`` as malformed
    # even though the whitespace itself would round-trip.
    if not reason.strip():
        raise ValueError("reason must be non-empty")
    # Reject every character that ``str.splitlines()`` treats as a line
    # break.  Parsing is line-oriented (the parser only consumes the first
    # line that starts with the schedule prefix), and the grammar has no
    # newline escape, so any line-breaking character would silently
    # truncate the reason on round-trip.  ``str.splitlines()`` recognises
    # \n, \r, \r\n, \v, \f, \x1c, \x1d, \x1e, \x85, \u2028, \u2029.
    if len(reason.splitlines()) > 1 or any(
        ch in reason
        for ch in (
            "\n",
            "\r",
            "\v",
            "\f",
            "\x1c",
            "\x1d",
            "\x1e",
            "\x85",
            "\u2028",
            "\u2029",
        )
    ):
        raise ValueError("reason must not contain line-breaking characters")
    escaped = reason.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def format_schedule_comment(
    *,
    not_before: datetime,
    reason: str,
    not_after: Optional[datetime] = None,
) -> str:
    """Render the canonical ``Symphony-Schedule:`` comment body.

    Datetimes are emitted in ISO 8601 UTC with ``+00:00`` offset.  Caller is
    responsible for supplying timezone-aware datetimes; naive values raise
    ``ValueError``.
    """
    if not_before.tzinfo is None:
        raise ValueError("not_before must be timezone-aware")
    if not_after is not None and not_after.tzinfo is None:
        raise ValueError("not_after must be timezone-aware")
    if not_after is not None and not_after < not_before:
        raise ValueError("not_after must be >= not_before")
    parts = [
        SCHEDULE_PREFIX,
        f"not_before={not_before.astimezone(timezone.utc).isoformat()}",
    ]
    if not_after is not None:
        parts.append(f"not_after={not_after.astimezone(timezone.utc).isoformat()}")
    parts.append(f"reason={_quote_reason(reason)}")
    return " ".join(parts)


def format_cancellation_comment(*, reason: str) -> str:
    """Render the canonical ``Symphony-Schedule-Cancelled:`` comment body."""
    return f"{CANCELLATION_PREFIX} reason={_quote_reason(reason)}"


# ---------------------------------------------------------------------------
# Latest-event-wins selection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateComment:
    """Minimal projection of a Plane comment used by ``latest_event``.

    Callers typically build this from the ``comments/`` listing without
    coupling the parser to a particular HTTP client.
    """

    body: object
    comment_id: Optional[str] = None
    created_at: Optional[datetime] = None
    api_order: Optional[int] = None


def _make_sort_key(use_api_order: bool):
    """Return a sort-key callable parameterised by api_order availability.

    Sort precedence (plan task 3.8):

    1. ``created_at`` ascending; ``None`` sorts oldest so any explicit
       timestamp wins over an unstamped comment.
    2. ``api_order`` only when **all** candidates supplied one.  When any
       candidate lacks ``api_order`` we skip this level entirely so a
       partial Plane payload cannot override the documented comment_id
       tie-break in step 3.
    3. ``comment_id`` lexicographic.  This is the documented deterministic
       tie-breaker required by the plan and runs before falling back to
       the comment's index in the original input list.
    4. Original input index as a final stability anchor.
    """

    def _key(item: tuple[int, CandidateComment]):
        idx, comment = item
        created = comment.created_at
        created_key = created.timestamp() if created is not None else float("-inf")
        cid = comment.comment_id or ""
        if use_api_order:
            return (created_key, comment.api_order, cid, idx)
        return (created_key, cid, idx)

    return _key


def latest_event(
    comments: Sequence[CandidateComment] | Iterable[CandidateComment],
) -> Optional[ScheduleEvent]:
    """Return the latest schedule control-plane event, or ``None``.

    Behavior:
    * Non-control-plane comments (no recognised prefix) are ignored.
    * If the latest control-plane comment fails to parse,
      ``ScheduleParseError`` is raised; callers MUST treat this as a hard
      failure and NOT fall back to older events.  This matches plan task 7.2.
    * If no control-plane comment exists, returns ``None``.
    """
    # First isolate the control-plane candidates only.  This guarantees that
    # ordering decisions (notably the api_order tie-break) are made over the
    # set of comments we will actually choose from — unrelated chatter must
    # not perturb the winner (regression: round-4 audit finding 3).
    control_plane: list[tuple[int, CandidateComment]] = []
    for idx, comment in enumerate(comments):
        normalised = normalize_comment_body(comment.body)
        is_control = any(
            line.lstrip().startswith((SCHEDULE_PREFIX, CANCELLATION_PREFIX))
            for line in normalised.splitlines()
        )
        if is_control:
            control_plane.append((idx, comment))

    if not control_plane:
        return None

    # Honour api_order only when EVERY control-plane candidate has one; if any
    # is missing fall through to comment_id (the documented tiebreak).
    use_api_order = all(c.api_order is not None for _, c in control_plane)
    control_plane.sort(key=_make_sort_key(use_api_order))
    _, latest = control_plane[-1]
    return parse_schedule_comment(
        latest.body,
        comment_id=latest.comment_id,
        comment_created_at=latest.created_at,
    )


__all__ = [
    "CandidateComment",
    "CANCELLATION_PREFIX",
    "ScheduleEvent",
    "ScheduleEventType",
    "ScheduleParseError",
    "SCHEDULE_PREFIX",
    "format_cancellation_comment",
    "format_schedule_comment",
    "latest_event",
    "normalize_comment_body",
    "parse_schedule_comment",
]
