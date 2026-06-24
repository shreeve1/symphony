---
id: 109
title: Mutual exclusion — co-run lock gate on candidate selection
status: review
blocked_by: [105, 108]
locks: [scheduler]
priority: 1
created: 2026-06-23
---

## What to build

Per ADR-0021 (P2, Layer 3). `blocked_by` forces *order*; `locks` forbids *co-run*.
Two issues with an overlapping `locks` set may run in any order but never at the
same time, so their isolated worktrees don't collide at FF-merge. Add the lock
filter to candidate selection (same place the dependency gate from 106 lives —
`tracker_podium.list_candidates` / the `run_tick` selection step).

- Compute the **held lock set** = union of `locks` across currently in-flight
  issues for the binding (the scheduler already tracks `in_flight_ids` per
  `_DispatchState`).
- A `todo` candidate is lock-eligible only if its `locks` set is **disjoint** from
  the held set. Non-disjoint candidates **stay `todo`** (no new state), exactly
  like the dependency gate.
- Within a single tick's selection, maintain a "claimed-this-tick" lock set: once a
  candidate is selected, add its locks; skip any later candidate whose locks
  intersect the claimed set. This stops two lock-sharing candidates from both
  dispatching in the same tick.
- Empty `locks` ⇒ never excluded by this rule (independent work parallelizes up to
  `run_cap`).
- Order of filters in selection: dependency-satisfied → lock-disjoint-from-held →
  lock-disjoint-from-claimed-this-tick → dispatch up to `_effective_run_cap`.

## Acceptance criteria

- [ ] Two `todo` issues sharing a lock label do not run concurrently — the second
      stays `todo` until the first reaches a terminal outcome.
- [ ] Two `todo` issues with disjoint (or empty) locks still parallelize up to
      `run_cap` in separate worktrees.
- [ ] A candidate whose locks intersect an in-flight issue's locks is withheld.
- [ ] No issue is transitioned to the `blocked` state by this gate.

## Verification

`uv run pytest tests/test_scheduler.py -q`
