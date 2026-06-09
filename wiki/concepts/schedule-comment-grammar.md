---
title: Schedule comment grammar
type: concept
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - schedule.py
confidence: high
tags: [scheduling, parser, plane-comment, iso8601, html-normalisation]
---

# Schedule comment grammar

The Symphony ticket-scheduling control plane lives on Plane as two append-only structured comment shapes plus the `scheduled` label. Source of truth: `schedule.py` (pure parser — no I/O).

## Two comment shapes

```text
Symphony-Schedule: not_before=<iso8601> [not_after=<iso8601>] reason="..."
Symphony-Schedule-Cancelled: reason="..."
```

Prefix constants exported from the module: `SCHEDULE_PREFIX`, `CANCELLATION_PREFIX` [source: schedule.py#101-102].

## Hard invariants

- `not_before` MUST be ISO 8601 with explicit UTC offset or trailing `Z`. Naive datetimes and natural language rejected.
- `reason` required and non-empty for both event kinds.
- `not_after` is **advisory only**. When present, must parse and must not be earlier than `not_before`.
- Latest valid schedule or cancellation event wins. Comments sorted by `created_at` with deterministic tiebreaker on Plane comment ID / API order so reschedules and races are stable.
- **No fallback to older schedules when the latest event is malformed.** Caller treats `ScheduleParseError` on the latest event as a blocking condition and writes a parse-error audit comment [source: schedule.py#9-21].

## Recognized keys

- `Symphony-Schedule:` accepts `{not_before, not_after, reason}` only.
- `Symphony-Schedule-Cancelled:` accepts `{reason}` only.
- Unknown keys → `ScheduleParseError("unknown keys for ...")` [source: schedule.py#106-107, 563-567].

## Token grammar

```text
key="quoted value with spaces"
key=bare-value-without-spaces
```

Only these two forms. Reason values must always be quoted when they contain whitespace, eliminating ambiguity. Missing whitespace between tokens (e.g. `reason="x"not_after=...`) raises `ScheduleParseError` rather than silently splitting [source: schedule.py#114-124, 487-496].

## HTML normalisation (the tricky part)

Plane stores comments as rich text. The parser does **quote-aware** normalisation:

- Outside quoted spans: `<br>`, `<br/>`, `<p ...>`, `</p>` replaced with single space (not newline — Plane uses `<br>` to soft-wrap a single logical line; the parser inspects the first prefix-bearing line). HTML entities decoded via `html.unescape`. Runs of horizontal whitespace collapsed to single space.
- Inside literal-quote spans (operator typed `"`): copy verbatim; respect `\X` escapes; never touch entities or whitespace.
- Inside decoded-entity quote spans (Plane encoded `"` as `&quot;`): continue decoding entities inside; respect `\X`; preserve whitespace and wrapper tags. Plane uses `reason=&quot;rotate &amp; restart&quot;` for rich-text payloads, so inner `&amp;` becomes `&` [source: schedule.py#139-260].

## Public API

| Symbol | Purpose |
|---|---|
| `ScheduleEventType` | enum: `SCHEDULE` \| `CANCELLATION` |
| `ScheduleEvent` | frozen dataclass: event_type, reason, not_before, not_after, comment_id, comment_created_at, raw_comment + `is_schedule`/`is_cancellation` properties |
| `ScheduleParseError` | raised for any structural failure on a recognised prefix |
| `parse_schedule_comment(body, *, comment_id, comment_created_at)` | parse single comment → `ScheduleEvent` or `None` (not a control-plane comment) or raise |
| `format_schedule_comment(...)` | serialise to comment body (round-trips through parser) |
| `format_cancellation_comment(*, reason)` | serialise cancellation event |
| `normalize_comment_body(body)` | exposed for callers that need the HTML-stripped form |
| `CandidateComment` | input dataclass: body, comment_id, created_at, api_order |
| `latest_event(comments)` | sort + pick winner; isolates control-plane candidates first so unrelated chatter cannot perturb the winner (round-4 audit finding 3) |

[source: schedule.py#42-94, 502-553, 656-787]

## Sort precedence (winner determination)

Per `_make_sort_key` [source: schedule.py#705-732]:

1. `created_at` ascending (None sorts oldest, so any explicit timestamp wins over an unstamped comment).
2. `api_order` — **only when every control-plane candidate has one**. If any lacks `api_order`, this level is skipped so a partial Plane payload cannot override the documented `comment_id` tiebreak.
3. `comment_id` lexicographic — documented deterministic tiebreaker.
4. Original input index — final stability anchor.

## Why the parser is pure

Callers fetch comments via the Plane adapter and pass them in. The parser does no I/O, so it composes cleanly with whatever adapter or test transport supplies the comments [source: schedule.py#23-24].

## Related

- [Symphony operations — Ticket scheduling section](symphony-operations.md)
- [Plan history — symphony-ticket-scheduling](../analyses/symphony-plan-history.md#symphony-ticket-scheduling)
- C-0012 (label-only fallback rule)
