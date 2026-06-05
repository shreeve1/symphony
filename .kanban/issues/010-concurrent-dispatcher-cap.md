---
id: 010
title: Concurrent dispatcher at cap=2–3
status: review
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

- [ ] The dispatcher launches multiple Runs concurrently against the same repo with no working-tree collision.
- [ ] The live-run semaphore enforces the cap: the (cap+1)th Run waits until a slot frees.
- [ ] A timed-out/cancelled Run releases its semaphore slot and cleans up its worktree (and tmux session if claude).
- [ ] Per-tick single-flock serialization is removed.
- [ ] Suite green, including a concurrent-Runs test asserting cap enforcement and isolation.

## Verification

`uv run pytest`

## Blocked by

- Blocked by #4
- Blocked by #5
