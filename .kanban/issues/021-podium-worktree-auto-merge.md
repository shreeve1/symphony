---
id: 021
title: Worktree opt-in + auto-merge on Done (fast-forward only)
status: done
blocked_by: [020]
parent: null
priority: 0
created: 2026-06-10
updated: 2026-06-11
actor: ralph
previous_status: review
---

## What to build

Per ADR-0005: `issue.worktree_active` (default false) toggles per-Issue
persistent worktree behaviour. When the operator toggles it on, the engine
creates a per-Issue branch + worktree the next time the issue dispatches.
When the issue transitions to Done, Podium fast-forward-merges the branch
into `base_branch` and tears the worktree down.

Mechanics:

1. New module `web/api/worktree.py` (or extend `run_worktree.py` if
   resurrected) — creates a worktree at
   `worktrees/<binding>/<issue_id>` on the bound repo, on a branch
   named `podium/<binding>/<issue_id>`.
2. Dispatch path: when `worktree_active=true`, the agent runs in that
   worktree path; when false, the agent runs in the repo checkout
   (thin-engine v2 behaviour, unchanged).
3. On `state` transition to `done` AND `worktree_active=true`:
   - **Precheck:** run `git status --porcelain` in the *base* repo
     (not the worktree). If non-empty, ABORT — base checkout is dirty;
     post a blocked comment "Auto-merge halted: base checkout has
     uncommitted changes" and stop. Same comment shape as the other
     abort paths below.
   - Attempt `git merge --ff-only podium/<binding>/<issue_id>` into
     `base_branch`.
   - On success: delete the worktree, delete the branch ref, leave
     `worktree_active` true (operator decides whether to reset).
   - On conflict / diverged base / force-pushed base: ABORT merge,
     leave worktree intact, post a blocked comment to `comments_md`:
     "Auto-merge halted: <reason>. Inspect worktree at <path>."
   - No merge-commit fallback, no force-push, no rebase.
4. Toggling `worktree_active` from true → false while the worktree
   exists posts a comment ("Worktree archived; not torn down — toggle
   on again or delete manually"). Do NOT auto-delete; preserve operator
   intent.

## Acceptance criteria

- [x] `worktree.py` creates the worktree at the documented path with the documented branch name (test asserts both).
- [x] Dispatch flow: an issue with `worktree_active=true` runs `pi` inside the worktree path (test mocks `pi`, asserts `cwd` arg).
- [x] State transition `* → done` with `worktree_active=true` triggers `git merge --ff-only`. Test sets up a fixture repo where the branch is ahead of base, asserts the merge runs and the worktree is removed.
- [x] Conflict test: fixture repo where base has diverged; merge attempt aborts, worktree remains, blocked comment appended to `comments_md`.
- [x] Force-pushed base test: same outcome as conflict.
- [x] Dirty base-checkout test: fixture has uncommitted edits in the base repo; merge attempt aborts before running `git merge`; blocked comment posted; worktree intact.
- [x] Toggling `worktree_active` off does NOT delete an existing worktree; a comment is appended noting the archive.
- [x] Playwright `worktree.spec.ts`: toggle the chip on, file an issue, watch the chip render the worktree path; toggle to done, watch the chip clear.

## Verification

```
cd /home/james/symphony && uv run pytest && \
cd web/frontend && pnpm test:e2e
```

## Blocked by

- #020 (real engine dispatch through Podium is the host for this behaviour)

## Implementation Notes

Added Podium worktree helpers, dispatch-time worktree cwd selection, API merge/archive handling for `worktree_active`, worktree metadata UI, and regression coverage for merge success, conflict/diverged base, force-pushed base, dirty base, toggle-off archive, and Playwright chip behavior.
