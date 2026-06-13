---
id: 046
title: Unify Symphony agent output contract and clean the comment stream
status: done
updated: 2026-06-13
actor: james
blocked_by: []
parent: null
priority: 2
created: 2026-06-13
---

## What to build

The `SYMPHONY_RESULT`/`SYMPHONY_SUMMARY` boilerplate was duplicated across `claude_runner._wrap_prompt` and each binding's `WORKFLOW.md`, the single-line `SYMPHONY_SUMMARY:` marker truncated multi-line agent output, and every closing comment carried a machine `Timeline` footer plus a `Symphony claimed at <ts>` claim comment that cluttered the human-facing comment stream (which is re-injected into the next prompt as context).

Unify the agent output contract behind one source and strip the machine noise:

1. Add a single `OUTPUT_CONTRACT` block in `prompt_renderer.py`, appended to every rendered prompt so the pi and claude runners receive identical instructions from one place.
2. Introduce a multi-line `SYMPHONY_SUMMARY_BEGIN` / `SYMPHONY_SUMMARY_END` block. Parse the last block across streams, strip ANSI and machine marker lines, and bound it (4000 chars; head 2500 / tail 1200 on overflow) so a runaway agent cannot dump its transcript into a comment. Keep the legacy single-line `SYMPHONY_SUMMARY:` marker as a fallback.
3. Post the summary verbatim — drop the `### Symphony AI Summary` wrapper in `tracker_podium.post_comment`.
4. Remove the `Timeline` footer (`_format_timeline`, `_CODE_SHA`, the now-unused `resolve_code_sha` import in `scheduler.py`) and stop posting the `Symphony claimed at` comment. Claim time now comes from the Run record's `started_at` via `_run_started_at`, with comment-parse fallback retained for adapters without a Run store (Plane).

## Acceptance criteria

- [x] One `OUTPUT_CONTRACT` source appended to every prompt; pi and claude wrap text reference it.
- [x] Multi-line `SYMPHONY_SUMMARY_BEGIN/END` block preferred over the single-line marker, which still works as fallback.
- [x] Summary posted verbatim (no `### Symphony AI Summary` wrapper).
- [x] No `Timeline` footer and no `Symphony claimed at` comment on terminal-state comments.
- [x] `_run_started_at` resolves claim time from the latest Run record; Plane falls back to comment parsing.
- [x] `uv run pytest` green.
- [x] Live `homelab` and `trading` `WORKFLOW.md` updated to the new block with the single-line fallback noted.

## Verification

`cd /home/james/symphony && uv run pytest`

## Implementation Notes

- `OUTPUT_CONTRACT` lives in `prompt_renderer.py` and is appended after the issue block in `render_prompt`.
- `_parse_summary_block` / `_bound_summary_block` added to `scheduler.py`; `_extract_summary` prefers the block, then the single-line marker.
- Blocked-path stderr summary now appends only when there is no summary block (verbatim summary is left clean).
- `tracker_podium.post_comment` writes the body stripped, no header wrapper.
- 694 passed, 1 skipped via `uv run pytest`.

## Blocked by

- None
