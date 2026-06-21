---
id: 94
title: SYMPHONY_SCHEDULE output marker — parse + output contract + INFRA_PREAMBLE
status: review
blocked_by: [93]
parent: null
priority: 0
created: 2026-06-21
updated: 2026-06-21
actor: ralph
---

## What to build

The fourth terminal output marker so a CLI-less Podium infra agent can request a
schedule (it cannot mutate the tracker directly — INFRA_PREAMBLE rule 13). Pure
parsing + renderer-constant wording; no scheduler behavior wired here (that is
issue 95).

1. **Marker parsing** (`scheduler/markers.py`): add `_SCHEDULE_MARKER_RE` matching
   a single column-0 line `SYMPHONY_SCHEDULE: not_before=<next_window|iso8601-with-offset> reason="..."`
   (case-insensitive, MULTILINE, ANSI-stripped, mirroring `_RESULT_MARKER_RE`).
   Add `_parse_schedule_marker(stdout) -> tuple[datetime, str] | None` returning
   the LAST marker's timezone-aware `not_before` (resolving `next_window` via the
   issue-93 `next_maintenance_window` helper) and a NON-EMPTY reason. `reason` is
   REQUIRED — `format_schedule_comment`/`parse_schedule_comment` reject empty
   reasons. Reuse `schedule.py` token/datetime parsing for explicit timestamps;
   return `None` on no-match; flag malformed/missing `not_before` or empty reason.
2. **Strip from blocks**: extend `_MARKER_LINE_RE` (`scheduler/markers.py:30`) to
   include `SCHEDULE` so the marker line is removed from summary/question blocks.
3. **Re-export** `_parse_schedule_marker` from `scheduler/__init__.py` (mirror the
   `_parse_result_marker as _parse_result_marker` import block at `:69-72`).
4. **Output contract** (`prompt_renderer.OUTPUT_CONTRACT`): document the marker as
   the 4th terminal outcome (mechanism only, no policy): "Deferring to a
   maintenance window: emit `SYMPHONY_SCHEDULE: not_before=<next_window|iso8601-with-offset> reason="..."`
   plus a summary block — use `next_window` unless a specific time is required."
5. **INFRA_PREAMBLE** (`prompt_renderer.INFRA_PREAMBLE` rules 13/15): stop
   hardcoding "exactly one `SYMPHONY_RESULT`"; defer terminal-outcome syntax to the
   appended `## Symphony output contract` (which now includes `SYMPHONY_SCHEDULE`).
   Mechanism wording only — no medium-risk/window policy (that is homelab CLAUDE.md).

## Acceptance criteria

- [ ] `_parse_schedule_marker` parses a valid marker (explicit ISO + offset) → `(datetime, reason)`; last-occurrence wins; ANSI-wrapped lines parse.
- [ ] `not_before=next_window` resolves via `next_maintenance_window`.
- [ ] Missing/empty reason, missing/malformed `not_before`, or a bare natural-language timestamp → `None`/flagged (not silently accepted).
- [ ] `_MARKER_LINE_RE` strips a `SYMPHONY_SCHEDULE:` line out of a `SYMPHONY_SUMMARY_BEGIN/END` block.
- [ ] `OUTPUT_CONTRACT` documents the marker with the `<next_window|iso8601-with-offset>` form; `INFRA_PREAMBLE` no longer mandates only `SYMPHONY_RESULT`.
- [ ] Existing prompt-renderer tests still pass.

## Verification

`uv run pytest tests/test_schedule.py tests/test_prompt_renderer.py tests/test_prompt_renderer_podium.py -q`

## Blocked by

- Blocked by #93 (uses `next_maintenance_window` / `next_window` resolution).
