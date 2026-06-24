---
id: 111
title: MANUAL — deploy P2 conflict-free parallel dispatch (live Alembic 0010 + restart + verify)
status: pending
blocked_by: [106, 107, 108, 109, 110, 113]
priority: 2
created: 2026-06-23
---

## What to build

Hard-to-reverse live step from ADR-0021 (P2). Operator-gated; do not auto-run
unattended.

- Back up the live Podium SQLite DB first (`scripts/podium-backup.sh`).
- Apply Alembic migration 0010 (blocked_by + locks) to the live DB; confirm
  runtime schema == head.
- `next build` web frontend (atomic staging swap per deploy.sh) for the chips.
- Restart `symphony-host.service` (the live dispatcher) so the dependency gate,
  worktree-default, and lock gate take effect; restart `podium-api`/`podium-web`.
- **Live verify** on the `symphony` binding with a throwaway set, all `todo` at
  once:
  - **Dependency**: B `blocked_by: [A]` + independent C → A and C dispatch in
    parallel (separate worktrees), B stays `todo` until A `done`, then B dispatches.
  - **Isolation**: confirm A and C each run in their own `worktree_dir(...)` (not
    the shared `/home/james/symphony` checkout); worktrees removed on terminal.
  - **Mutual exclusion**: D `locks: [x]` + E `locks: [x]`, both eligible → only one
    dispatches at a time; the other stays `todo` until the first is terminal.
  - **Merge contention (113)**: A and C both edit (different files) off the same
    base and finish close together → both land; the second's FF-fail is rescued by
    rebase-onto-base + retry (journal `merge_succeeded` after a rebase), neither
    left blocked, both worktrees removed.
  - Then archive the throwaway issues.
- **Calibration checks** (ADR risks): a resumed/warm (claude_persist) run re-enters
  the same deterministic worktree; worktrees don't accumulate after terminal
  outcomes.

## Acceptance criteria

- [ ] DB backed up before migration; 0010 applied; schema parity confirmed.
- [ ] B does not dispatch while A is unfinished; dispatches after A is done.
- [ ] Independent A + C run in parallel up to run_cap, each in its own worktree.
- [ ] Lock-sharing D + E never co-run; second waits until first is terminal.
- [ ] Worktrees removed on terminal outcome; warm-session resume re-enters cleanly.
- [ ] Two near-simultaneous landings off the same base both merge (rebase-retry
      rescues the second FF-fail); neither is left blocked with a leftover worktree.

## Verification

Prose (live host): journal shows A+C dispatched concurrently in distinct
worktrees, B withheld until A done then dispatched, D/E serialized on the shared
lock; clean `symphony-host` restart; no orphan worktrees.
