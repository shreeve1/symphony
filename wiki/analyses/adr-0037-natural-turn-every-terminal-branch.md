---
title: "ADR-0037 — Surface the captured natural turn on every terminal branch"
type: analysis
status: promoted
created: 2026-07-13
updated: 2026-07-13
sources:
  - docs/adr/0037-surface-natural-turn-on-every-terminal-branch.md
  - scheduler/__init__.py
  - scheduler/sanitize.py
  - scheduler/markers.py
  - agent_runner.py
  - tests/test_scheduler.py
confidence: high
tags: [adr, output-contract, comments, natural-turn, captured-turn, scheduler, terminal-branch, schedule, retry-exhaustion, accepted]
---

# ADR-0037 — Surface the captured natural turn on every terminal branch

**Status: `accepted`** — implemented 2026-07-13 (grill-me session; symptom on issue 379 + schedule/retry paths).

## Problem

ADR-0022 (C-0308) decided the issue comment is the agent's **captured natural turn** — for pi, `"".join(drain.assistant_parts)` from `_drain_rpc_events`; for claude, the transcript turn — with the `SYMPHONY_SUMMARY` block downgraded to an optional fallback [source: wiki/analyses/adr-0022-post-captured-turn-not-forced-summary.md]. But `_capture_natural_turn` (`scheduler/sanitize.py`) was wired into `_classify_terminal` (`scheduler/__init__.py`) at a **single** point — the clean review/done fall-through. Every other terminal branch either ran *before* that capture or *discarded* it and re-derived the comment via `_extract_summary`, which requires a `SYMPHONY_SUMMARY_BEGIN/END` block and otherwise returns `None` → a terse stub [source: scheduler/__init__.py; source: scheduler/sanitize.py].

Operator symptom (issue 379 grill): completion comments were routinely terse/empty, forcing run-history archaeology (`runs/<id>.log`) to see what the agent actually said. There was **no separate "SYMPHONY_COMPLETE capture system"** to remove (the operator's framing) — the mechanism was already the ADR-0022 natural-turn capture; it just wasn't reached on most branches [source: docs/adr/0037-surface-natural-turn-on-every-terminal-branch.md].

## The dropped-prose branches (before the fix)

- **Timeout / non-zero exit** — ran before the line-~1240 capture; posted only "Agent timed out…" / "Agent failed with exit code N…" via `_block_issue(msg)`; `_extract_summary` fed only the run row [source: scheduler/__init__.py].
- **`SYMPHONY_SCHEDULE`** — reassigned `summary = _extract_summary(...)`, discarding the captured turn; the schedule notice posted, the agent's prose survived only in the run log. Live example: **run 1656 / issue 67** — schedule notice posted, the "27 remaining Debian packages…" analysis lost to `runs/1656.log` [source: runs/1656.log].
- **Permission-gate / approval-gate / malformed-schedule** — posted only the diagnostic string.
- **Three retry-exhaustion blocks** — `_block_retry_ceiling`, `_maybe_retry_stall` cap-exhausted, `_maybe_transient_review_retry` cap-exhausted: terminal blocked states *inside* the retry helpers, which run before the capture; posted only "…retry cap exhausted after N retries." [source: scheduler/__init__.py].

## The out-of-scope half — comment ≠ CLI

The operator also reported the posted output reading "different than the CLI." This is **structural and deliberately not fixed**: for pi RPC runs the captured stdout is `_assistant_delta`-filtered — assistant `text_delta` events only, with thinking deltas, tool calls, and tool results excluded (`agent_runner.py` `_assistant_delta`, `_drain_rpc_events`). So a comment can never be CLI-fidelity; it is prose-only by capture design. ADR-0037 fixes only the "prose was dropped entirely" half [source: agent_runner.py; source: docs/adr/0037-surface-natural-turn-on-every-terminal-branch.md].

## Decision & implementation

Hoist the single `_capture_natural_turn(...)` call to the **top** of `_classify_terminal` (before the retry gate), compute `summary` once, and make it the source every terminal branch consumes:

- **Diagnostic-comment branches** (timeout, non-zero exit, permission-gate, approval-gate, malformed-schedule, retry-exhaustion): append the turn to `msg` when prose exists (`msg += f"\n\n{summary}"`); keep the bare diagnostic when empty.
- **Schedule branch**: post `f"{schedule_comment}\n\n{summary}"` instead of discarding the turn.
- **Retry helpers** (`_block_retry_ceiling`, `_maybe_retry_stall`, `_maybe_transient_review_retry`): gained an optional `summary` param threaded from `_classify_terminal`, used **only** in their terminal-blocked branches.
- `_extract_summary` stays the fallback everywhere — used only when the turn is genuinely empty, preserving the `SYMPHONY_SUMMARY`-override contract [source: scheduler/__init__.py].

**Deliberately unchanged**: the re-dispatching retry branches (verdict=`retry`) still post only `format_retry_marker` / `format_stall_retry_marker` and requeue — the issue runs again so nothing is permanently lost, and prose on a transient marker would be noise. Bounding stays at `DISPLAY_MAX_CHARS` (12 K) inside `_capture_natural_turn`; the 2 KB `REPORT_MAX_BYTES` path is untouched (still run-row / gate classification only, per C-0257) [source: scheduler/sanitize.py; source: scheduler/markers.py].

## Consequences & verification

- Only a genuinely empty turn (pi emitted zero text deltas, e.g. **run 1659's `*No output*`** — pi's own placeholder, not a Symphony string) now falls back to a terse label [source: runs/1659.log].
- Failure comments are longer (diagnostic **plus** turn); `_block_issue` already bounds the Telegram notifier body via `NOTIFY_REASON_MAX_CHARS`, so alerts stay under 4096 chars [source: scheduler/__init__.py].
- This **reverses** the earlier explicit decision that failure comments omit stdout — two tests encoded it (`test_run_tick_omits_stdout_in_blocked_comments`, renamed to `test_run_tick_surfaces_natural_turn_in_blocked_comments`; and the "partial" assertion in `test_run_tick_stderr_appears_in_blocked_timeout_comment`), flipped to assert the turn now appears [source: tests/test_scheduler.py].
- Regression coverage for the schedule and retry-exhaustion branches: `test_schedule_marker_schedules_issue` (asserts the natural turn appears in the scheduled comment), `test_fourth_stall_failure_blocks_at_combined_ceiling` and `test_transient_review_retry_cap_blocks_and_notifies` (assert the turn appears in the exhaustion block comment). A revert probe confirmed each new assertion fails pre-fix. 239 scheduler + transient-retry tests pass [source: tests/test_scheduler.py].

Deploy = `symphony-host.service` restart (the live dispatcher imports the scheduler at process start). Not committed/deployed at capture time.
