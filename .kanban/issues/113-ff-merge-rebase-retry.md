---
id: 113
title: Merge-contention fix — FF-fail rebase-onto-base + retry, then block
status: in-progress
blocked_by: []
locks: [web-api]
priority: 1
created: 2026-06-23
---

## What to build

Per ADR-0021 (P2) merge-contention gap, operator-approved 2026-06-23. With
worktree-per-run default ON (108), two independent issues dispatch in parallel off
the same `base_branch`. The first lands and advances base; the second's
`git merge --ff-only` (`web/api/worktree.py:162`) now fails because base moved →
the issue is forced to `blocked` and its worktree is left behind. No rebase/retry
exists today. This makes P2 *not* conflict-free: every parallel pair leaves a
blocked leftover.

Fix — close the FF-fail path in `merge_worktree`:

- On `--ff-only` failure (the `CalledProcessError` branch at `worktree.py:170`),
  before aborting+returning, attempt **one in-process rebase** of the worktree
  branch onto the advanced base: `git -C <worktree_dir> rebase <base_branch>`
  (local refs only — no remote contact, so the agents-don't-touch-remotes rule
  in `prompt_renderer.py` is untouched).
- Clean rebase → retry the FF merge (now a true fast-forward) → `None` (success);
  caller proceeds to `cleanup_worktree` as today.
- Rebase **conflict** → `git -C <worktree_dir> rebase --abort` → return the block
  error string with the worktree path. Conflicts need judgement Symphony does not
  have unattended, so block + leave the worktree intact for inspection is the
  honest terminal — this is the "then block" the operator approved.

ponytail: in-process single rebase, not an agent re-dispatch+counter. A non-
conflicting rebase is deterministic and needs no agent, so the re-dispatch
plumbing (and a cap counter) is YAGNI here. Upgrade path if real conflicts get
common: re-dispatch the agent to resolve, capped like `MAX_COMMIT_REDISPATCH`.

## Acceptance criteria

- [ ] Two branches off the same base: land the first; the second's FF-fail is
      rescued by rebase-onto-base + FF retry and lands cleanly (worktree removed).
- [ ] A genuine rebase conflict aborts the rebase and returns the block error;
      worktree left intact, no partial merge in the base checkout.
- [ ] Success path unchanged when the first FF already fast-forwards (no rebase
      attempted).

## Verification

`uv run pytest web/api/tests/test_worktree.py -q`
