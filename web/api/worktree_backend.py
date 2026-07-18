"""WorktreeBackend seam: one landing algorithm, two mechanics.

The worktree-landing state machine (``_maybe_merge_worktree`` in main.py) is
identical whether the Run Worktree lives on the local filesystem or on a remote
SSH host — the only difference is *which* git operations run and how a dirty
base checkout is handled. Previously that algorithm was written twice, once per
mechanism, so any landing-logic fix had to be mirrored across both branches.

This module isolates the two mechanics behind a common async interface. The
engine (main.py) drives the landing algorithm against a ``WorktreeBackend``
without knowing whether it is talking to the local FS or a remote host. Two
implementations = a real seam (not a hypothetical one), so the abstraction earns
its keep.

The interface is deliberately five methods, matching exactly the ops the landing
algorithm branches on:

- ``exists`` — is the worktree present? (drift guard)
- ``is_dirty`` — did the agent leave uncommitted work? (ADR-0014 re-dispatch)
- ``base_blocks_merge`` — a merge-blocking reason for a dirty base, or None.
  Local returns None (``merge_worktree_preserving_base_wip`` stashes base WIP,
  issue wins); remote returns a block message (it cannot safely stash a remote
  base).
- ``merge`` — attempt the FF-only land; None on success, else the block reason.
- ``remove`` — tear the worktree down after a proven land.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Protocol

from config import RemotePolicy

try:  # pragma: no cover - import style mirrors main.py's dual path
    from web.api.worktree import (
        branch_name,
        cleanup_worktree,
        merge_worktree_preserving_base_wip,
        worktree_dir,
        worktree_exists,
        worktree_is_dirty,
    )
except ImportError:  # pragma: no cover - uvicorn --app-dir web/api path
    from worktree import (  # type: ignore[no-redef]
        branch_name,
        cleanup_worktree,
        merge_worktree_preserving_base_wip,
        worktree_dir,
        worktree_exists,
        worktree_is_dirty,
    )


class WorktreeBackend(Protocol):
    """The worktree ops the landing algorithm branches on, mechanism-agnostic."""

    async def exists(self) -> bool: ...

    async def is_dirty(self) -> bool: ...

    async def base_blocks_merge(self) -> str | None: ...

    async def merge(self, base_branch: str) -> str | None: ...

    async def remove(self) -> None: ...


@dataclass
class LocalWorktreeBackend:
    """Local-filesystem worktree mechanics."""

    repo_path: Path
    binding_name: str
    issue_id: str

    async def exists(self) -> bool:
        return await asyncio.to_thread(
            worktree_exists, self.repo_path, self.binding_name, self.issue_id
        )

    async def is_dirty(self) -> bool:
        return await asyncio.to_thread(
            worktree_is_dirty, self.repo_path, self.binding_name, self.issue_id
        )

    async def base_blocks_merge(self) -> str | None:
        # Local merge stashes base WIP (issue wins), so a dirty base never blocks.
        return None

    async def merge(self, base_branch: str) -> str | None:
        return await asyncio.to_thread(
            merge_worktree_preserving_base_wip,
            self.repo_path,
            self.binding_name,
            self.issue_id,
            base_branch,
        )

    async def remove(self) -> None:
        await asyncio.to_thread(
            cleanup_worktree, self.repo_path, self.binding_name, self.issue_id
        )


@dataclass
class RemoteWorktreeBackend:
    """Remote SSH worktree mechanics."""

    remote: RemotePolicy
    repo_path: Path
    binding_name: str
    issue_id: str

    def _rw(self):
        return import_module("remote_worktree")

    async def exists(self) -> bool:
        return await asyncio.to_thread(
            self._rw().worktree_exists,
            self.remote,
            self.repo_path,
            self.binding_name,
            self.issue_id,
        )

    async def is_dirty(self) -> bool:
        return await asyncio.to_thread(
            self._rw().worktree_is_dirty,
            self.remote,
            self.repo_path,
            self.binding_name,
            self.issue_id,
        )

    async def base_blocks_merge(self) -> str | None:
        if await asyncio.to_thread(
            self._rw().base_repo_dirty, self.remote, self.repo_path
        ):
            branch = branch_name(self.binding_name, self.issue_id)
            wt_path = worktree_dir(self.repo_path, self.binding_name, self.issue_id)
            return (
                "Auto-merge halted: remote base checkout has uncommitted changes. "
                f"Branch {branch} is unmerged. Worktree at {wt_path} is intact."
            )
        return None

    async def merge(self, base_branch: str) -> str | None:
        return await asyncio.to_thread(
            self._rw().merge_worktree,
            self.remote,
            self.repo_path,
            self.binding_name,
            self.issue_id,
            base_branch,
        )

    async def remove(self) -> None:
        await asyncio.to_thread(
            self._rw().remove_worktree,
            self.remote,
            self.repo_path,
            self.binding_name,
            self.issue_id,
        )


def worktree_backend_for(
    repo_path: Path,
    binding_name: str,
    issue_id: str,
    remote: RemotePolicy | None,
) -> WorktreeBackend:
    """Pick the backend for a binding: remote when a RemotePolicy is present."""
    if remote is not None:
        return RemoteWorktreeBackend(remote, repo_path, binding_name, issue_id)
    return LocalWorktreeBackend(repo_path, binding_name, issue_id)


# ---------------------------------------------------------------------------
# Sync review/reland seam
# ---------------------------------------------------------------------------
#
# The synchronous review/reland path in ``scheduler/reland.py`` needs the same
# local-vs-remote pick as the async landing algorithm above, but over a
# different (wider) set of ops and without asyncio. It previously repeated the
# ``if binding.is_remote`` branch across five helpers. This is the twin of
# ``WorktreeBackend``: one factory picks the mechanism once, so reland's helpers
# become one-line delegations.
#
# Local ops resolve through the ``worktree_facade`` / ``web.api.worktree``
# modules by attribute at call time (not bound at import) so the existing
# monkeypatch surface (``worktree_facade.worktree_is_dirty`` etc.) still works.


class ReviewWorktreeBackend(Protocol):
    """The worktree ops the review/reland path branches on, mechanism-agnostic."""

    def is_dirty(self) -> bool: ...

    def diff_empty(self, base_branch: str) -> bool: ...

    def base_dirty(self) -> bool: ...

    def base_on_branch(self, base_branch: str) -> bool: ...

    def land(self, base_branch: str) -> str | None: ...


@dataclass
class LocalReviewWorktreeBackend:
    """Local-filesystem review/reland mechanics."""

    repo_path: Path
    binding_name: str
    issue_id: str

    def is_dirty(self) -> bool:
        facade = import_module("worktree_facade")
        return bool(
            facade.worktree_is_dirty(self.repo_path, self.binding_name, self.issue_id)
        )

    def diff_empty(self, base_branch: str) -> bool:
        facade = import_module("worktree_facade")
        return bool(
            facade.worktree_diff_empty(
                self.repo_path, self.binding_name, self.issue_id, base_branch
            )
        )

    def base_dirty(self) -> bool:
        # base_repo_dirty is not exported by worktree_facade.__all__; go direct.
        wt = import_module("web.api.worktree")
        return bool(wt.base_repo_dirty(self.repo_path))

    def base_on_branch(self, base_branch: str) -> bool:
        wt = import_module("web.api.worktree")
        return bool(wt.base_repo_branch(self.repo_path, base_branch))

    def land(self, base_branch: str) -> str | None:
        facade = import_module("worktree_facade")
        result = facade.land_worktree(
            self.repo_path, self.binding_name, self.issue_id, base_branch
        )
        return result if result is None else str(result)


@dataclass
class RemoteReviewWorktreeBackend:
    """Remote SSH review/reland mechanics."""

    remote: RemotePolicy
    repo_path: Path
    binding_name: str
    issue_id: str

    def _rw(self):
        return import_module("remote_worktree")

    def is_dirty(self) -> bool:
        return bool(
            self._rw().worktree_is_dirty(
                self.remote, self.repo_path, self.binding_name, self.issue_id
            )
        )

    def diff_empty(self, base_branch: str) -> bool:
        # remote_worktree offers no diff-empty check, so "nothing to review"
        # cannot be proven over SSH: report not-empty (unknown is not empty).
        # This limitation lives here, at the remote mechanic, not in reland.
        return False

    def base_dirty(self) -> bool:
        return bool(self._rw().base_repo_dirty(self.remote, self.repo_path))

    def base_on_branch(self, base_branch: str) -> bool:
        return bool(
            self._rw().base_repo_branch(self.remote, self.repo_path, base_branch)
        )

    def land(self, base_branch: str) -> str | None:
        result = self._rw().land_worktree(
            self.remote, self.repo_path, self.binding_name, self.issue_id, base_branch
        )
        return result if result is None else str(result)


def review_worktree_backend_for(
    repo_path: Path,
    binding_name: str,
    issue_id: str,
    remote: RemotePolicy | None,
) -> ReviewWorktreeBackend:
    """Pick the review/reland backend: remote when a RemotePolicy is present."""
    if remote is not None:
        return RemoteReviewWorktreeBackend(remote, repo_path, binding_name, issue_id)
    return LocalReviewWorktreeBackend(repo_path, binding_name, issue_id)
