---
id: 109
title: Mutual exclusion — co-run lock gate on candidate selection
status: done
blocked_by: [105, 108]
locks: [scheduler]
priority: 1
created: 2026-06-23
updated: 2026-06-24
actor: ralph
action_reviewed: 2026-06-24
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

- [x] Two `todo` issues sharing a lock label do not run concurrently — the second
      stays `todo` until the first reaches a terminal outcome.
- [x] Two `todo` issues with disjoint (or empty) locks still parallelize up to
      `run_cap` in separate worktrees.
- [x] A candidate whose locks intersect an in-flight issue's locks is withheld.
- [x] No issue is transitioned to the `blocked` state by this gate.

## Verification

`uv run pytest tests/test_scheduler.py -q`

## Implementation Notes

Added `locks` to `CandidateIssue`, hydrated Podium candidates from `issue.locks`, and taught the dispatch reservation gate to track in-flight lock labels. Conflicting candidates are skipped without state changes; disjoint/empty locks can still dispatch up to the configured cap.
