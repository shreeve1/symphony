---
id: 119
title: Review-run terminal — provenance-gated auto-land + fail→blocked
status: in-progress
blocked_by: [114, 117, 118]
locks: [scheduler]
priority: 1
created: 2026-06-24
---

## What to build

Per ADR-0023, apply the terminal outcome when a **review** run finishes (the run
dispatched by 118 — identified by the `### Symphony Review` marker being present).
Pass-terminal is provenance-gated by `auto_land` (114); fail-terminal is uniform.

- Distinguish a review-run terminal from an implement-run terminal by the
  `### Symphony Review` marker in `comments_md` (present ⇒ this finishing run is the
  review). Implement-run terminals keep today's behavior (park `in_review`).
- **Pass** (review emits `SYMPHONY_RESULT: done`):
  - First require a **clean, committed worktree**. If the worktree is dirty
    (`worktree_is_dirty`, already re-exported via `worktree_facade`), treat it as a
    fail → `blocked` (the reviewer was mandated to commit; a dirty tree is a failure,
    NOT a redispatch-to-`todo`). This is what keeps the issue out of the implement
    pool.
  - `auto_land = true` (slicer-authored): transition `in_review → done` and call
    `land_worktree(repo, binding, issue_id, base_branch)` (117 — pure merge+113
    rebase-retry+cleanup). `land_worktree` returns a block-reason on conflict ⇒
    transition to `blocked` with that reason (worktree left for inspection). Success
    ⇒ issue is `done`, worktree removed. Result: unattended merge into `main`. Notify
    on the merge (reuse `_notify_review`/add a merged notification — an unattended
    merge to `main` must not be silent).
  - `auto_land = false` (operator-authored, default): the issue STAYS in `in_review`
    (review-passed, awaiting operator merge); no `land_worktree`, no state change.
    The existing operator done-merge path (`_maybe_merge_worktree`) handles the
    eventual manual merge.
- **Fail** (review emits `SYMPHONY_RESULT: blocked`, or dirty-worktree above, or the
  119-companion driver backstop in 120 fails): transition `in_review → blocked` with
  the reason (feeds `blocked_reconciler` + ADR-0021 dependency gate; downstream
  `blocked_by` issues stay gated). Applies to BOTH provenances.
- **Single review per issue** (no retry): the `### Symphony Review` marker means the
  issue is never re-reviewed, so a failed review is terminal `blocked` — a retry would
  only re-review unchanged code (the reviewer already had its fix-in-place shot).

## Acceptance criteria

- [ ] Review pass + `auto_land=true` + clean worktree → `in_review`→`done` and
      `land_worktree` lands the branch (113 rebase-retry applies); worktree removed;
      merge notified.
- [ ] Review pass + `auto_land=false` → issue stays `in_review` (no auto-merge, no
      state change).
- [ ] Review pass but dirty worktree → `blocked` (NOT redispatched to `todo`).
- [ ] Review fail (either provenance) → `in_review`→`blocked`; downstream `blocked_by`
      issues stay gated.
- [ ] A `land_worktree` rebase conflict → `blocked` with the reason; no partial merge
      in base.

## Verification

`uv run pytest tests/test_scheduler.py web/api/tests/test_worktree.py -q`
