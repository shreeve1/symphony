---
id: 125
title: Stall retry markers + counter + combined ceiling + _classify_terminal path
status: done
blocked_by: [124]
locks: [redispatch_core, scheduler, transient_retry]
priority: 1
created: 2026-06-25
updated: 2026-06-26
actor: ralph
---

## What to build

Add stall-aware retry classification so frozen-agent runs get one stall retry before blocking, and the combined retry ceiling gates all retry paths.

1. **`redispatch_core.py` markers/counters:**
   - `STALL_MARKER_PREFIX = "### Symphony Retry (stall"`, `STALL_MARKER_RE` (mirrors `RETRY_MARKER_RE` with `stall` instead of `transient`)
   - `format_stall_retry_marker(attempt, now) -> str`: `"### Symphony Retry (stall · N) · <iso>"`
   - `count_stall_retries(comments_md) -> int`: counts `STALL_MARKER_RE` matches
   - `count_all_retries(comments_md) -> int`: `count_retries() + count_stall_retries()`
   - `MAX_STALL_RETRIES = 1`, `MAX_COMBINED_RETRIES = 3`

2. **`scheduler/transient_retry.py` re-exports:** export all new stall symbols.

3. **`scheduler/__init__.py` — combined ceiling pre-check:** At the top of `_classify_terminal`'s `result.timed_out or result.exit_code != 0` block, before any transient retry dispatch:
   - Short-circuit with cheap snapshot: `count_all_retries(candidate.comments_md or "")`. If `>= MAX_COMBINED_RETRIES`, block immediately.
   - Otherwise fetch fresh `comments_md = await _retry_comments_text(adapter, candidate)` (try/except; on failure fall back to `candidate.comments_md or ""` and log WARNING). If `total >= MAX_COMBINED_RETRIES`, block immediately.
   - Blocking pattern: finish run record as `failed`/`blocked`, `_block_issue()` with ceiling-exhausted message, return `TickResult(True, "combined-ceiling-exhausted", ...)`.
   - Pass the fetched `comments_md` into `_maybe_retry_stall()`, `_maybe_transient_review_retry()`, and `_maybe_retry_transient_implement()`. For `_maybe_transient_review_retry`: accept optional `comments_md` param; when provided, use it instead of `getattr(candidate, "comments_md", "")`.

4. **`_maybe_retry_stall()` helper:** If `STALL_WATCHDOG_SENTINEL in result.stderr` and cap not exhausted: write `### Symphony Retry (stall · N)` marker, transition implement→`STATE_TODO` or review→`STATE_IN_REVIEW` (with `RELAND_PENDING`). If cap exhausted: block.

## Acceptance criteria

- [x] `format_stall_retry_marker(1, now)` produces `"### Symphony Retry (stall · 1) · <iso>"`
- [x] `count_stall_retries()` counts stall markers, ignores transient markers
- [x] `count_all_retries()` sums transient + stall counts
- [x] Combined ceiling: `count_all_retries() >= 3` blocks when 2 transients + 1 stall present
- [x] Stall sentinel triggers retry (cap not exhausted), marker written
- [x] Second stall on same issue → cap exhausted → blocked
- [x] Combined ceiling pre-check stops ALL retries: 3 of any kind present → blocks
- [x] Stall sentinel does NOT match `is_transient()`
- [x] Stall during review dispatch → retry, issue stays `in_review`, `RELAND_PENDING` present
- [x] Transient retry blocked by combined ceiling: 3 retries of any kind → blocks
- [x] All existing transient retry and scheduler tests pass

## Verification

```bash
uv run pytest tests/test_transient_retry.py tests/test_scheduler.py -x -q
```

## Blocked by

- Blocked by #124

## Implementation Notes

Added stall retry marker/counter exports, combined retry-ceiling classification, and stall retry/review reland handling. Backfilled scheduler tests covering stall retry, stall cap exhaustion, review reland, and the mixed transient+stall combined ceiling.
