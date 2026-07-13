---
status: accepted
relates-to: ADR-0022 (post the agent's captured turn as the comment — this finishes its reach), ADR-0019 (the same pi `assistant_parts` stream), C-0355 (the `is_claude` separator gate on the same `_capture_natural_turn`)
decided-with: James, 2026-07-13 (grill-me; symptom = terse/empty completion comments on issue 379 and schedule/retry paths, forcing run-history archaeology to see what the agent actually said)
---

# Surface the captured natural turn on every terminal branch, not just the clean-completion path

## Context

ADR-0022 established that Symphony posts the agent's **captured natural turn**
(pi `assistant_parts` / claude transcript turn) as the issue comment, with the
`SYMPHONY_SUMMARY` block downgraded to an optional fallback. But the capture
(`_capture_natural_turn`, `scheduler/sanitize.py`) was only wired into a *single*
point in `_classify_terminal` (`scheduler/__init__.py`) — the clean
review/done fall-through. Every other terminal branch either ran **before** that
capture or **discarded** it and re-derived a comment via `_extract_summary`,
which needs a `SYMPHONY_SUMMARY_BEGIN/END` block and otherwise yields `None` →
a terse stub:

- **Timeout / non-zero exit** — ran before the capture; posted only
  "Agent timed out…" / "Agent failed with exit code N…".
- **`SYMPHONY_SCHEDULE`** — overwrote the captured turn with
  `_extract_summary`; the agent's real prose survived only in `runs/<id>.log`
  (observed: run 1656 / issue 67 — the schedule notice posted, the "27 remaining
  Debian packages…" analysis was lost to the log).
- **Permission-gate / approval-gate / malformed-schedule** — posted only the
  diagnostic string.
- **Three retry-exhaustion blocks** (`_block_retry_ceiling`,
  `_maybe_retry_stall` cap, `_maybe_transient_review_retry` cap) — terminal
  blocked states inside the retry helpers, which run before the capture; posted
  only "…retry cap exhausted after N retries."

The operator symptom: completion comments were routinely terse/empty, and the
real output had to be dug out of run history — and even when prose *was* posted,
it read differently from the interactive CLI. (The second half is structural and
out of scope: the captured turn is assistant `text_delta` only — never tool
calls / results — so a comment can never be CLI-fidelity. This ADR fixes only
the "prose was dropped entirely" half.)

There was no separate "SYMPHONY_COMPLETE capture system" to remove (the
operator's framing) — the mechanism was already the ADR-0022 natural-turn
capture; it simply wasn't reached on most terminal branches.

## Decision

Hoist the single `_capture_natural_turn(...)` call to the **top** of
`_classify_terminal` (before the retry gate), compute `summary` once, and make
that captured turn the source every terminal branch consumes:

- **Comment-is-the-diagnostic branches** (timeout, non-zero exit,
  permission-gate, approval-gate, malformed-schedule, retry-exhaustion blocks):
  append the natural turn to the diagnostic `msg` when prose exists
  (`msg += f"\n\n{summary}"`); keep the bare diagnostic when the turn is empty.
- **Schedule branch**: post the schedule notice **plus** the natural turn
  (`f"{schedule_comment}\n\n{summary}"`), instead of discarding it.
- **Retry helpers** (`_block_retry_ceiling`, `_maybe_retry_stall`,
  `_maybe_transient_review_retry`): take an optional `summary` param threaded
  from `_classify_terminal`, used only in their **terminal-blocked** branches.
- `_extract_summary` remains the fallback everywhere, used only when the natural
  turn is genuinely empty — preserving the `SYMPHONY_SUMMARY`-override contract.

Deliberately **not** changed: the re-dispatching retry branches (verdict=`retry`)
still post only their `format_retry_marker` / `format_stall_retry_marker` and
requeue — the issue runs again, so nothing is permanently lost, and adding prose
to a transient retry marker would just be noise. Comment bounding stays at
`_capture_natural_turn`'s existing `DISPLAY_MAX_CHARS` (12 K); the 2 KB
`REPORT_MAX_BYTES` path is untouched (still used only for run-row / gate
classification, per C-0257).

## Consequences

- Every path that posts a *terminal* comment now surfaces the agent's prose when
  it produced any; only a genuinely empty turn (pi emitted zero text deltas, e.g.
  run 1659's `*No output*`) falls back to a terse label.
- Failure comments (blocked / timeout / gate / exhaustion) are now longer — they
  carry the diagnostic **and** the turn. `_block_issue` already bounds the
  Telegram notifier body (`NOTIFY_REASON_MAX_CHARS`), so alerts stay under the
  4096-char limit.
- This is the reversal of the earlier explicit decision that failure comments
  should *omit* stdout (two `test_scheduler.py` tests encoded it); those tests
  were flipped to assert the turn now appears.
