---
id: 106
title: Gate dispatch on dependencies (todo eligible only when blockers done)
status: pending
blocked_by: [105]
locks: [scheduler]
priority: 1
created: 2026-06-23
---

## What to build

Per ADR-0021, make candidate selection dependency-aware. This is the core slice:
it converts "all todo issues run in parallel" into "independent issues parallelize
(up to run_cap), dependents wait."

- In `tracker_podium.list_candidates`, exclude any `todo` issue whose `blocked_by`
  contains an id NOT in `done` or `archived`. Excluded issues **stay `todo`** —
  do NOT transition them to `blocked` (that state is agent-failure; keep distinct).
- **Unresolved blocker id** (no such issue) ⇒ treat as satisfied and log a
  warning (`dependency_blocker_unresolved issue=<id> blocker=<id>`). Prevents a
  typo/cross-binding ref from wedging an issue forever.
- Eligible independent issues continue to dispatch under the existing
  `run_cap` semaphore (no concurrency change). A dependent becomes eligible on
  the next tick after its last blocker closes.
- Resolve blocker states with one query per tick (fetch states for the binding's
  issues once), not N+1 per candidate.

## Acceptance criteria

- [ ] A `todo` issue with an unsatisfied blocker is not returned as a candidate and stays `todo`.
- [ ] Once all blockers are `done`/`archived`, it becomes a candidate next tick.
- [ ] Independent `todo` issues still dispatch in parallel up to `run_cap`.
- [ ] Unresolved blocker id → issue is eligible + a warning is logged.

## Verification

`uv run pytest tests/test_scheduler.py -q`
