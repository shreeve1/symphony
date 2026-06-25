---
id: 106
title: Gate dispatch on dependencies (todo eligible only when blockers done)
status: done
blocked_by: [105]
locks: [scheduler]
priority: 1
created: 2026-06-23
updated: 2026-06-24
actor: ralph
action_reviewed: 2026-06-24
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

- [x] A `todo` issue with an unsatisfied blocker is not returned as a candidate and stays `todo`.
- [x] Once all blockers are `done`/`archived`, it becomes a candidate next tick.
- [x] Independent `todo` issues still dispatch in parallel up to `run_cap`.
- [x] Unresolved blocker id → issue is eligible + a warning is logged.

## Verification

`uv run pytest tests/test_scheduler.py -q`

## Implementation Notes

`tracker_podium.list_candidates` now loads the binding's issue states once per tick, filters `todo` candidates with unfinished dependencies, leaves withheld issues in `todo`, and warns while allowing unresolved blocker ids. Review repair made that dependency snapshot unbounded so page-capped terminal issues cannot hide candidates or blockers. Added scheduler-suite coverage for unsatisfied, satisfied, independent, unresolved, and page-cap dependency cases.
