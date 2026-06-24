---
id: 122
title: MANUAL — deploy ADR-0023 review phase (live Alembic 0011 + restart + verify)
status: in-progress
blocked_by: [115, 118, 119, 120, 121]
priority: 2
created: 2026-06-24
updated: 2026-06-24
---

## What to build

Hard-to-reverse live step from ADR-0023. Operator-gated; do not auto-run unattended.
Sequence AFTER ADR-0021's deploy (slice 111) — this builds on worktree-per-run
default-ON (108) and the 113 rebase-retry merge path (extracted into `land_worktree`
by 117). Precondition: 108 must be live, so review-phase issues actually carry
`worktree_active=true`; otherwise an auto_land issue flips `done` but the merge
no-ops.

- Back up the live Podium SQLite DB first (`scripts/podium-backup.sh`).
- Apply Alembic migration `0011` (`auto_land`) to the live DB; confirm runtime schema
  == head.
- Restart `symphony-host.service` (the live dispatcher) so review selection (118),
  terminal handling (119), and the backstop (120) take effect; restart
  `podium-api`/`podium-web` for the create-path (115) and the refactored
  `_maybe_merge_worktree` (117) (`next build` first per the podium-web drop-in note).
- **Live verify** on the `symphony` binding with a throwaway batch:
  - **Slicer-authored auto-land:** create a small issue via `/podium-issues`
    (`auto_land=true`) with a real runnable `## Verification` → implement run parks
    `in_review` → next tick a **review** run is selected from `in_review` and
    dispatched into the SAME `worktree_dir` (marker `### Symphony Review` written) →
    review passes + backstop verification exits 0 + worktree clean → `in_review`→
    `done`, `land_worktree` lands the branch into `main` (journal `merge_succeeded`),
    worktree removed, merge notified — no operator action.
  - **Operator-authored gate:** create a UI/operator issue (`auto_land=false`) →
    implement → review pass → issue STAYS `in_review` (no auto-merge) until the
    operator merges.
  - **Fail path:** an issue whose verification cannot pass → review run flips it
    `in_review`→`blocked` (not silently done); single review (no re-review);
    downstream `blocked_by` issues stay gated.
  - **Backstop override:** a review that emits `done` but whose runnable
    `## Verification` exits non-zero is overridden to `blocked`; worktree not landed.
  - **Dirty-worktree guard:** a review pass on a dirty worktree → `blocked` (NOT
    redispatched to `todo`); confirm the issue does not re-enter the implement pool.
  - Then archive the throwaway issues.
- **Calibration:** the review run re-enters the implement run's worktree (same
  `worktree_dir`, no second worktree); worktrees removed on terminal; each run takes
  its own `run_cap` slot (review is a normal dispatch, ~2x runs/issue, not a held
  inline phase); confirm `latest_verdict`/`latest_run_state` now reflect the review
  run and nothing downstream misbehaves.

## Acceptance criteria

- [ ] DB backed up before migration; 0011 applied; schema parity confirmed.
- [ ] Slicer-authored issue: implement→`in_review`→review→auto-land to `main` on pass,
      no operator action; worktree removed; merge notified.
- [ ] Operator-authored issue: implement→review pass→stays `in_review`, no auto-merge.
- [ ] Failing review → `blocked` (not done); single review; dependents stay gated.
- [ ] Backstop overrides an over-optimistic `done`; dirty worktree → `blocked` not
      `todo`.
- [ ] Review run re-enters the same worktree; no orphan worktrees after terminal.

## Verification

Prose (live host): journal shows, for a slicer-authored issue, an implement run
parking `in_review`, then a review run selected from `in_review` in the same worktree,
then `merge_succeeded` + worktree removed with no operator action; an operator-authored
issue stays `in_review` on review pass; a failing/over-optimistic review → `blocked`;
clean `symphony-host` restart.
