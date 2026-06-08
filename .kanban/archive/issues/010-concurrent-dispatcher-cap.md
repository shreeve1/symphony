---
id: 010
title: Concurrent dispatcher at cap=2–3
status: done
blocked_by: [4, 5]
updated: 2026-06-05
actor: ralph
parent: null
priority: 0
created: 2026-06-04
---

## What to build

Restructure the tick from "acquire one flock, dispatch exactly one issue" into a
**concurrent dispatcher** that launches and supervises N in-flight Runs as async
tasks, bounded by the live-run semaphore (raise the cap from 1 to 2–3). The cap
is necessary but not sufficient: per-run worktree isolation (#004) is what makes
same-repo parallelism safe, so multiple agents can work the same repo at the same
instant. Timeouts and cancellation must tear down the Run's worktree (and tmux
session, for claude) cleanly.

See `docs/adr/0003-worktree-per-run-with-global-concurrency-cap.md`. The repo
already uses `pytest-asyncio` (`asyncio_mode = "auto"`).

## Acceptance criteria

- [x] The dispatcher launches multiple Runs concurrently against the same repo with no working-tree collision.
- [x] The live-run semaphore enforces the cap: the (cap+1)th Run waits until a slot frees.
- [x] A timed-out/cancelled Run releases its semaphore slot and cleans up its worktree (and tmux session if claude).
- [x] Per-tick single-flock serialization is removed.
- [x] Suite green, including a concurrent-Runs test asserting cap enforcement and isolation.

## Verification

`uv run pytest`

## Blocked by

- Blocked by #4
- Blocked by #5

## Implementation Notes

Actionable review blockers resolved:

- `run_tick()` no longer acquires the live-run semaphore; `_dispatch_one()` is the single semaphore owner.
- `run_loop()` waits on active dispatch tasks with `asyncio.wait(..., FIRST_COMPLETED)` instead of spinning while tasks are active.
- Agent execution runs through `asyncio.to_thread(...)`, allowing multiple synchronous agents to overlap under async dispatcher tasks.
- Run cleanup now executes on cancellation and calls deterministic tmux cleanup after worktree removal; tmux cleanup covers Claude's private socket and tolerates hosts without tmux installed.
- Added regression coverage for cap+1 waiting, overlapping same-repo worktrees, duplicate in-flight suppression, scheduled-release reservation/failure races, cancellation semaphore/worktree/tmux cleanup, and private-socket tmux cleanup.

Verification: `uv run pytest` passed (399 tests). Critical LSP diagnostics for touched files reported no diagnostics.
