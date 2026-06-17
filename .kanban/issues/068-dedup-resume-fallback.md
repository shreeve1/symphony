---
id: 068
title: Dedup resume-fallback retry block
status: pending
blocked_by: [64]
parent: null
priority: 0
created: 2026-06-17
---

## What to build

Finding L1-02 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`), first step of the Phase 4 scheduler decomposition. The resume-failed → fall-back-to-fresh-dispatch sequence (~85 LOC) appears twice: `scheduler.py:1521-1605` (dispatch-exception path) and `:1615-1697` (nonzero-exit path) — near-identical (finish run failed → log resume_failed → reset candidate to fresh sha → re-render → re-start run record → re-dispatch → on crash finish+block).

Extract `_dispatch_with_resume_fallback` taking the candidate + reason, returning the fresh `AgentResult` (or the terminal `TickResult`). Both paths invoke it. Must land before the `run_tick` decomposition (#070).

## Acceptance criteria

- [ ] `_dispatch_with_resume_fallback` exists and is invoked from both the dispatch-exception and nonzero-exit paths.
- [ ] No duplicated ~85-LOC resume-fallback block remains in `scheduler.py`.
- [ ] Behavior unchanged; `uv run pytest` passes.

## Verification

`uv run pytest`

Live-dispatch-path change: before this issue is marked done, James runs the `symphony-restart` skill and confirms `symphony_started`, `reconcile_startup_*`, and `dispatch_completed` in the journal.

## Blocked by

- Blocked by #064 (serializes the `scheduler.py` edit ordering; tracker_types repoint lands first).
