---
id: 004
title: Run Worktree lifecycle at cap=1 (replace global flock)
status: done
blocked_by: [2, 3]
updated: 2026-06-04
actor: ralph
parent: null
priority: 0
created: 2026-06-04
action_reviewed: 2026-06-04
---

## What to build

Give every Run its own isolated `git worktree` + branch instead of operating on
the shared checkout. A deterministic `run-id → worktree path / branch name /
tmux session` naming scheme is defined up front (so durable signals can be
matched back to Runs in #5). The worktree is created at dispatch and torn down
after the Verdict is reconciled, with guaranteed cleanup on crash/timeout so an
orphaned worktree never wedges the repo.

Replace the single global `fcntl` flock (`scheduler.py:375`) with a live-run
semaphore set to **cap=1** — behavior stays serial for now, but the mechanism is
the semaphore, not the flock. `_auto_commit` (`scheduler.py:1466`) commits to the
run's own branch rather than the shared checkout, and never pushes.

See `docs/adr/0003-worktree-per-run-with-global-concurrency-cap.md`.

## Acceptance criteria

- [x] Each Run executes in its own worktree+branch created from the binding's base branch.
- [x] Worktree + branch names derive deterministically from the run id per the documented scheme.
- [x] Worktree is removed after the Verdict is reconciled, and on simulated crash/timeout (no orphan left behind).
- [x] The global flock is gone; a semaphore caps live Runs at 1.
- [x] `_auto_commit` lands commits on the Run's branch, not the shared checkout, and does not push.
- [x] Existing single-project pi dispatch still completes end-to-end (suite green).

## Verification

`uv run pytest`

## Blocked by

- Blocked by #2
- Blocked by #3

## Implementation Notes

Actionable review fixed the prior blockers:

- `PiAgentAdapter.__call__` now accepts and forwards `worktree_path` into `run_agent`, so production pi runs execute inside the per-Run worktree.
- Scheduler startup/dispatch paths now remove deterministic orphan worktrees before redispatch and during stale running reconciliation.
- Added regression coverage for adapter worktree propagation, pre-dispatch orphan recovery, timeout cleanup, and stale-running orphan cleanup.

Verification: `uv run pytest` passed (353 tests). Critical LSP diagnostics for touched files reported no diagnostics.
