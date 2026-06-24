---
id: 117
title: Extract process-neutral land_worktree (merge+land core, no state mutation)
status: review
blocked_by: [113]
locks: [web-api]
priority: 1
created: 2026-06-24
---

## What to build

Per ADR-0023, the scheduler (a separate process from `podium-api`) needs to land a
worktree after a passing review. Today the only merge path is
`_maybe_merge_worktree` (`web/api/main.py:1561`), which lives in the FastAPI app
module, takes a `sqlite3.Connection`, mutates issue state, and on a dirty worktree
calls `_redispatch_to_commit` (flips state to `todo`). The scheduler cannot and must
not import that — it would pull in FastAPI app construction, and the todo-flip
breaks the review flow. Extract a pure merge+land core both callers share.

- In `web/api/worktree.py`, add `land_worktree(repo_path, binding_name, issue_id,
  base_branch) -> str | None`: performs **only** the FF-merge + ADR-0021 slice 113
  rebase-onto-base-and-retry + `cleanup_worktree` on success. Returns `None` on
  success, or a block-reason string on failure (rebase conflict, etc.). It does
  **no** issue-state mutation and does **no** redispatch — pure git/worktree ops.
- Refactor `_maybe_merge_worktree` (`web/api/main.py`) to call `land_worktree` for
  its merge core, keeping its existing operator-merge behavior (state transitions,
  dirty→`_redispatch_to_commit`, comment-on-fail) as a thin wrapper around it.
  Behavior on the operator path must be unchanged.
- Re-export `land_worktree` from `worktree_facade.py` (add to the import shim and
  `__all__`) so the scheduler imports it the same way it already imports
  `create_worktree`/`remove_worktree`/`worktree_dir`.

## Acceptance criteria

- [ ] `land_worktree` exists in `web/api/worktree.py`; does merge + 113 rebase-retry +
      cleanup only; no issue-state mutation, no redispatch.
- [ ] `_maybe_merge_worktree` is refactored onto `land_worktree`; the operator-merge
      path (clean→merge, dirty→redispatch, fail→blocked comment) is behavior-identical.
- [ ] `worktree_facade` re-exports `land_worktree` (in the shim and `__all__`).

## Verification

`uv run pytest web/api/tests/test_worktree.py -q`
and `uv run python -m py_compile web/api/worktree.py web/api/main.py worktree_facade.py`
