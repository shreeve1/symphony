---
id: 005
title: Startup reconcile + reaper
status: review
updated: 2026-06-04
actor: ralph
blocked_by: [4]
parent: null
priority: 0
created: 2026-06-04
---

## What to build

Because Symphony keeps no database, the live-Run set and cap count are in-memory
and lost on a `symphony-host.service` restart — leaving orphaned worktrees and
detached tmux sessions. On startup, reconcile live state from durable signals:
existing `git worktree` entries, per-run-named tmux sessions, and Plane issues
left in the **Running** state (resolved via the Tracker Adapter). A reaper cleans
up orphans (remove dead worktrees, kill stale sessions, and reset or re-dispatch
issues stuck in Running) using the deterministic naming scheme from #004 to match
signals back to Runs.

See `docs/adr/0003-worktree-per-run-with-global-concurrency-cap.md`.

## Acceptance criteria

- [ ] On startup, an orphaned worktree from a prior process (no live Run) is detected and removed.
- [ ] A stale per-run tmux session with no owning process is killed.
- [ ] A Plane issue left in Running with no live Run is reconciled (reset/re-dispatched per policy).
- [ ] Reconcile matches durable signals to run ids via the #004 naming scheme.
- [ ] Tested with simulated leftovers (fixture worktrees/sessions/issues), suite green.

## Verification

`uv run pytest`

## Blocked by

- Blocked by #4
