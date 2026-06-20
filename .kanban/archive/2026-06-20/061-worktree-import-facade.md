---
id: 061
title: Single worktree import facade
status: done
blocked_by: []
parent: null
priority: 0
created: 2026-06-17
updated: 2026-06-17
actor: ralph
---

## What to build

Finding L2-04 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`). The `try: from web.api.worktree import create_worktree / except ImportError: from worktree import create_worktree` dual-import shim is copy-pasted at four sites: `agent_runner.py:253`, `claude_runner.py:583`, `scheduler.py:577`, `scheduler.py:1047`.

Add one facade module (e.g. `_worktree.py`) that performs the `web.api.worktree`-else-`worktree` try/except once and exposes `create_worktree`/`remove_worktree`/`worktree_exists`/`branch_name`/`worktree_dir`. Repoint the four call sites to import from the facade. (The deeper fix — a single stable home for `worktree` — is out of scope.)

## Acceptance criteria

- [x] A facade module performs the dual-import try/except exactly once and exposes the worktree functions.
- [x] All four call sites import worktree functions from the facade.
- [x] `grep -rn "from web.api.worktree import" *.py` shows only the facade module.
- [x] Behavior unchanged; `uv run pytest` passes.

## Verification

`uv run pytest`

## Blocked by

None — can start immediately.

## Implementation Notes

Added `worktree_facade.py` as the single compatibility shim for Podium worktree helpers. Repointed the four root call sites to load helpers through the facade while preserving lazy import behavior and remote-binding guards.
