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
