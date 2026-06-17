---
id: 054
title: Fast re-dispatch on operator reply
status: done
blocked_by: [047]
updated: 2026-06-13
parent: null
priority: 0
created: 2026-06-13
---

## What to build

Reduce the operator-reply → re-dispatch round-trip from a full poll tick (minutes) toward seconds, so the reply loop feels responsive.

Constraint: the scheduler is a SEPARATE process from the web/API (ADR-0006), so the reply endpoint cannot call dispatch directly. Use a wake signal:

- The reply endpoint (and any todo-flip that re-dispatches) writes/touches a wake sentinel file in a known runtime dir.
- The scheduler's poll loop watches for the sentinel each short interval; on detection it short-circuits its remaining poll wait and immediately runs a candidate scan, then clears the sentinel.

The sentinel must be safe across restarts and must not cause busy-looping when absent. If a sentinel-watch proves infeasible in the loop structure, the accepted fallback is a configurably shorter poll interval gated to recently-replied bindings — but the sentinel path is preferred.

## Acceptance criteria

- [x] Posting an operator reply writes the wake sentinel.
- [x] The scheduler loop detects the sentinel within one short interval, triggers an immediate candidate scan, and clears the sentinel.
- [x] Absent sentinel → no busy-loop; normal poll cadence is preserved.
- [x] Sentinel handling is restart-safe (stale sentinel on boot does not wedge the loop).
- [x] Round-trip improvement is covered by a test asserting the scan is triggered by the sentinel rather than waiting the full interval.

## Verification

`uv run pytest tests/test_scheduler*.py web/api/tests/test_reply.py -q`

## Blocked by

- Blocked by #047

## Implementation Notes

Added a shared wake-sentinel helper under `web/api/wake_signal.py`. Podium API touches the sentinel after successful operator replies and operator PATCH transitions to `todo`; failed replies do not wake the scheduler. Scheduler sleep now checks and consumes the sentinel at a one-second cadence, immediately continuing to the next dispatch scan when present while preserving normal poll cadence when absent.
