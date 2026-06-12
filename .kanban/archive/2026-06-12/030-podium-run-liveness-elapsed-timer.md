---
id: 030
title: Podium — run liveness elapsed timer + refresh-on-exit
status: done
blocked_by: [029]
parent: null
priority: 0
created: 2026-06-12
updated: 2026-06-12
actor: ralph
---

## What to build

Make an in-flight Run readably alive. Today `RunDetailPanel` is static:
`formatDuration` returns `—` until `ended_at` exists, and there is no
elapsed indicator while running. (A true live log tail is out of scope —
`agent_runner.py:272` uses `process.communicate(timeout=...)`, which blocks
until pi exits, so the log lands all-at-once; C-0113. Runs are bounded by
`run_timeout_ms` and orphans are reaped by the #022 restart reconciler.)

Decision: ADR-0006 — elapsed timer + refresh-on-exit, no streaming.

**1. Live elapsed timer.**

When a run's state is `running` (or `queued`→`running`) and `ended_at` is
null, show a ticking elapsed time computed from `started_at` (e.g.
`running 4m12s`) in `RunDetailPanel`'s duration cell. A 1s interval updates
the displayed value; clears on terminal state where `formatDuration` takes
over with the final wall-clock duration.

Surface the same running-elapsed affordance on the run row in
`RunHistoryList` (small "running Xm" indicator) so the operator sees it
without opening the detail panel. Note `RunHistoryList` currently renders
only `VerdictPill(run.verdict)` + model + `formatAge(started_at)` and does
**not** read `run.state` yet (`web/frontend/components/RunHistoryList.tsx`);
a non-terminal run has `verdict === null`, so add a `run.state`-driven
running badge rather than relying on the verdict pill.

**2. Refresh-on-exit.**

Relies on #029 gated polling: while the run is non-terminal the detail
panel already refetches, so metadata, final duration, and the log appear the
moment pi exits. No extra work beyond confirming the timer hands off to the
polled terminal row.

## Acceptance criteria

- [x] A `running` run with a `started_at` and null `ended_at` shows a ticking elapsed timer in the detail panel; it advances over time (Playwright with a fixture running run).
- [x] On terminal state the timer is replaced by the final `formatDuration` value (no double-render, no stuck timer).
- [x] `RunHistoryList` shows a running indicator for non-terminal runs.
- [x] Component/unit test covers the elapsed-format function for running vs terminal states.
- [x] `pnpm exec tsc --noEmit` passes.

## Implementation Notes

- Added shared `formatRunDuration()` / `isLiveElapsedRun()` helpers for active and terminal Run duration rendering.
- Added 1s live elapsed timers in the Run detail panel and Run history rows for queued/running runs.
- Updated Playwright coverage to prove the detail timer advances, terminal duration handoff occurs, and Run history shows the running indicator.

## Verification

```
cd /home/james/symphony && uv run pytest && \
cd web/frontend && pnpm exec tsc --noEmit && pnpm test:e2e
```

## Blocked by

- #029
