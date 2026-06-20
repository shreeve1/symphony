---
status: accepted
relates-to: ADR-0003 (worktree-per-run), ADR-0005 (worktree opt-in + FF-only auto-merge on done), ADR-0009 (session resume / park-and-reply re-dispatch)
context: worktree merge-on-done (#021) silently discards uncommitted worktree work via `git worktree remove --force` when the agent never committed
decided-with: James, 2026-06-18 (grill-me walkthrough of the worktree feature)
accepted: 2026-06-18 (implemented; see web/api/main.py:_maybe_merge_worktree, web/api/worktree.py:worktree_is_dirty)
---

# Worktree done-time: re-dispatch the agent to commit before merging, don't silently discard

## Context

Per-Issue worktrees (ADR-0003, opt-in per ADR-0005 / Podium #021) land work with an
FF-only merge when the operator transitions an Issue to `done`
(`web/api/main.py:_maybe_merge_worktree` → `web/api/worktree.py:merge_worktree`).
The merge path assumes the agent committed its work to the worktree branch
(`podium/<binding>/<issue_id>`). It does not verify that assumption.

The transition to `done` is always a **manual operator action**: a successful agent
run lands the Issue in `in_review` (`scheduler/__init__.py:1699,1772`), never `done`.
So merge-on-done never fires autonomously — the operator is always in the loop.

Two cases at `done`:

- **Case 1 — agent committed.** Branch is ahead of base, working tree clean.
  `merge --ff-only` lands the commits, then `cleanup_worktree` removes the worktree
  and branch. This works today and is unchanged by this ADR.
- **Case 2 — work exists but was never committed** (agent forgot, crashed mid-task,
  or its workflow did not commit). Branch == base, but the worktree working tree is
  dirty. The FF merge is a no-op "already up to date" → `cleanup_worktree` runs
  `git worktree remove --force` → **the uncommitted work is silently deleted** and the
  Issue shows green `done` with nothing landed. This is the only silent-data-loss path
  in the feature, and the green state hides it.

This matters most for the `symphony` self-binding (`type: coding`,
`repo_path: /home/james/symphony`): the worktree holds real scheduler changes, and a
silent discard loses agent work on the live infrastructure repo.

## Decision

At done-time, before any merge, classify the worktree:

1. **Clean + commits ahead of base (Case 1)** → FF-only merge + teardown, exactly as
   today.
2. **Dirty working tree (Case 2)** → do **not** merge or
   force-remove. Instead **re-dispatch the agent to commit its own work**, reusing the
   existing operator-reply machinery:

   _Refinement (implementation):_ the re-dispatch predicate is precisely **the worktree
   is dirty** (`git status --porcelain` non-empty inside the worktree), not "no commits
   ahead **or** dirty." A clean worktree with no commits ahead is genuinely empty — the
   agent produced nothing — so re-dispatching it would be a pointless loop; it falls
   through to today's harmless no-op FF merge + teardown. A worktree that is dirty *and*
   has commits ahead (a partial commit) still re-dispatches, so partial work is never
   landed.

   - synthesize an `### Operator Reply` note in `comments_md` instructing the agent to
     `git add -A && git commit` its worktree changes (and reminding it of the
     pre-commit test obligation), then signal done;
   - flip the Issue `state` to `todo` (the same atomic re-dispatch the
     `POST /api/issues/{id}/reply` endpoint performs, `web/api/main.py:1074-1113`).

   The scheduler re-dispatches; `create_worktree` is idempotent and the worktree
   **persists**, so the agent resumes in the *same dirty worktree* with its uncommitted
   changes intact (`prompt_renderer.py:278-290` surfaces the newest operator reply as
   the current request; session continuity re-feeds the transcript). The agent commits,
   the Issue returns to `in_review`, the operator marks `done`, and it is now Case 1.

3. **Loop guard.** Re-dispatch for an uncommitted worktree at most **twice** (counted
   by the synthetic commit-note marker already present in `comments_md` — no schema
   change). If the worktree is still uncommitted after the cap, **fall back to
   `blocked`** with a loud comment for manual handling. Falling back to `blocked`
   (rather than auto-committing) guarantees that work the agent never committed is
   never auto-landed into `main` — decisive for the self-binding, where untested or
   half-finished scheduler code must not reach `main` behind a green `done`.

4. The legitimate **non-FF block** path is unchanged: if the base advanced and the
   merge is not a fast-forward (conflict/diverged), revert to `blocked` with the
   existing comment. This ADR only removes the *silent-discard* path; it does not
   weaken the block-don't-corrupt posture.

The self-binding remains safe to enable: the base repo is on `main`, clean, with
`podium.db*` and build dirs gitignored (so `base_repo_dirty` does not false-trip); the
merge is equivalent to the manual `git pull`-into-`main` landing step; and it triggers
**no service restart** — landed code sits inert in the working tree until
`symphony-restart` is run.

## Considered options

- **Block immediately on Case 2 (no re-dispatch).** Safe but high-friction: every
  forgotten commit bounces to `blocked` and forces a manual commit or re-dispatch.
  Rejected as the primary path — the agent can fix its own omission.
- **Auto-commit `git add -A` at done-time.** Convenient, but Symphony makes the commit,
  bypassing the agent's pre-commit test obligation and message quality, and risks
  auto-landing half-finished/broken code into `main` (worst for the self-binding).
  Considered as the post-cap fallback and rejected in favor of `blocked` for the
  self-binding safety reason above.
- **Keep current behavior (silent force-remove).** Rejected — silent data loss masked
  by a green `done`.
