"""Stable import facade for Podium worktree helpers.

The implementation lives under ``web.api.worktree`` in the Podium package, but
some root modules can also be imported from contexts where that package path is
not available. Keep the compatibility import shim in one place.
"""

from __future__ import annotations

try:
    from web.api.worktree import (
        branch_name,
        create_worktree,
        remove_worktree,
        worktree_dir,
        worktree_exists,
    )
except ImportError:  # pragma: no cover - supports alternate import path
    from worktree import (  # type: ignore[no-redef]
        branch_name,
        create_worktree,
        remove_worktree,
        worktree_dir,
        worktree_exists,
    )

__all__ = [
    "branch_name",
    "create_worktree",
    "remove_worktree",
    "worktree_dir",
    "worktree_exists",
]
