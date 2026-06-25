---
id: 108
title: Isolation — worktree-per-run default-ON for local bindings
status: done
blocked_by: []
locks: [scheduler]
priority: 1
created: 2026-06-23
updated: 2026-06-24
actor: ralph
---

## What to build

Per ADR-0021 (P2, Layer 1 — the enabler). Two concurrent coding agents must NOT
share one checkout. Today `_worktree_run_fields` (`scheduler/__init__.py:385`)
returns `{}` unless the candidate has `worktree_active` (opt-in, off by default),
so `_dispatch_cwd` (line 427) falls back to the shared `config.homelab_repo_path`.
Flip the default so local runs are isolated.

- In `_worktree_run_fields`, treat worktree isolation as the **default for local
  (non-remote) bindings**. Replace the `if not worktree_active: return {}` opt-in
  gate with: remote binding → `{}` (unchanged; they cap at 1 and run in
  `binding.repo_path`); local binding → build worktree fields unless explicitly
  disabled (e.g. a `worktree_active is False` opt-OUT, or a config kill-switch
  `config.worktree_default` defaulting True — keep it one boolean).
- Worktree path stays deterministic: `worktree_dir(repo, binding, issue_id)`, so a
  resumed/warm session for the same issue re-enters the same path.
- Confirm `create_worktree` is invoked on dispatch and `remove_worktree` on
  terminal outcome (done/review/blocked) so worktrees don't accumulate. Reuse the
  existing ADR-0014 done-commit-redispatch + FF-only landing path; do not
  reimplement landing.
- Leave `_effective_run_cap` as-is (local = `run_cap`); isolation makes that cap
  safe instead of conflict-prone.

## Acceptance criteria

- [x] A local-binding `todo` issue dispatched with no explicit `worktree_active`
      runs in its own worktree (cwd = `worktree_dir(...)`), not the shared repo.
- [x] Remote bindings still run in `binding.repo_path` (no worktree fields).
- [x] Worktree is removed on terminal outcome; FF landing still applies the work.
- [x] An explicit opt-out (disabled flag) falls back to the shared repo.

## Verification

`uv run pytest tests/test_scheduler.py web/api/tests/test_worktree.py -q`

## Implementation Notes

Added `SymphonyConfig.worktree_default` (env `SYMPHONY_WORKTREE_DEFAULT`, default true) as the opt-out switch. Local coding bindings now default candidates into deterministic worktrees for dispatch/resume, remote bindings stay shared-repo, and Podium rows are marked `worktree_active=True` on dispatch so existing merge/cleanup paths still remove worktrees on terminal outcomes.
