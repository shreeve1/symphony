"""Unit tests for the WorktreeBackend seam.

These test the backend adapters in isolation (no FastAPI, no DB): the landing
algorithm's local-vs-remote mechanics live here, so the seam is verified without
driving a full patch_issue integration path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from config import RemotePolicy
from web.api.worktree_backend import (
    LocalWorktreeBackend,
    RemoteWorktreeBackend,
    worktree_backend_for,
)

REPO = Path("/repo")
REMOTE = RemotePolicy(host="n8n", user="agent", identity=None, host_alias=None)


def test_backend_selects_local_when_no_remote() -> None:
    backend = worktree_backend_for(REPO, "trading", "42", None)
    assert isinstance(backend, LocalWorktreeBackend)


def test_backend_selects_remote_when_remote_present() -> None:
    backend = worktree_backend_for(REPO, "n8n", "42", REMOTE)
    assert isinstance(backend, RemoteWorktreeBackend)


async def test_local_base_never_blocks() -> None:
    """Local merge stashes base WIP (issue wins), so a dirty base never blocks."""
    backend = LocalWorktreeBackend(REPO, "trading", "42")
    assert await backend.base_blocks_merge() is None


async def test_local_delegates_to_worktree_ops(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, tuple[Any, ...]]] = []
    import web.api.worktree_backend as wb

    monkeypatch.setattr(
        wb, "worktree_exists", lambda *a: calls.append(("exists", a)) or True
    )
    monkeypatch.setattr(
        wb, "worktree_is_dirty", lambda *a: calls.append(("dirty", a)) or False
    )
    monkeypatch.setattr(
        wb,
        "merge_worktree_preserving_base_wip",
        lambda *a: calls.append(("merge", a)) or None,
    )
    monkeypatch.setattr(wb, "cleanup_worktree", lambda *a: calls.append(("cleanup", a)))

    backend = LocalWorktreeBackend(REPO, "trading", "42")
    assert await backend.exists() is True
    assert await backend.is_dirty() is False
    assert await backend.merge("main") is None
    await backend.remove()

    assert [c[0] for c in calls] == ["exists", "dirty", "merge", "cleanup"]
    # All ops carry (repo_path, binding_name, issue_id); merge also base_branch.
    assert calls[0][1] == (REPO, "trading", "42")
    assert calls[2][1] == (REPO, "trading", "42", "main")


async def test_remote_base_blocks_when_dirty(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dirty remote base cannot be stashed safely → returns a block reason."""
    import remote_worktree

    monkeypatch.setattr(remote_worktree, "base_repo_dirty", lambda *a: True)
    backend = RemoteWorktreeBackend(REMOTE, REPO, "n8n", "42")
    reason = await backend.base_blocks_merge()
    assert reason is not None
    assert "remote base checkout has uncommitted changes" in reason


async def test_remote_base_clean_does_not_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import remote_worktree

    monkeypatch.setattr(remote_worktree, "base_repo_dirty", lambda *a: False)
    backend = RemoteWorktreeBackend(REMOTE, REPO, "n8n", "42")
    assert await backend.base_blocks_merge() is None


async def test_remote_delegates_to_remote_worktree_ops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import remote_worktree

    calls: list[str] = []
    monkeypatch.setattr(
        remote_worktree, "worktree_exists", lambda *a: calls.append("exists") or True
    )
    monkeypatch.setattr(
        remote_worktree, "worktree_is_dirty", lambda *a: calls.append("dirty") or False
    )
    monkeypatch.setattr(
        remote_worktree, "merge_worktree", lambda *a: calls.append("merge") or None
    )
    monkeypatch.setattr(
        remote_worktree, "remove_worktree", lambda *a: calls.append("remove")
    )

    backend = RemoteWorktreeBackend(REMOTE, REPO, "n8n", "42")
    assert await backend.exists() is True
    assert await backend.is_dirty() is False
    assert await backend.merge("main") is None
    await backend.remove()

    assert calls == ["exists", "dirty", "merge", "remove"]


# ── sync review/reland seam ────────────────────────────────────────────


def test_review_backend_selects_local_when_no_remote() -> None:
    from web.api.worktree_backend import (
        LocalReviewWorktreeBackend,
        review_worktree_backend_for,
    )

    backend = review_worktree_backend_for(REPO, "trading", "42", None)
    assert isinstance(backend, LocalReviewWorktreeBackend)


def test_review_backend_selects_remote_when_remote_present() -> None:
    from web.api.worktree_backend import (
        RemoteReviewWorktreeBackend,
        review_worktree_backend_for,
    )

    backend = review_worktree_backend_for(REPO, "n8n", "42", REMOTE)
    assert isinstance(backend, RemoteReviewWorktreeBackend)


def test_review_remote_diff_empty_is_always_false() -> None:
    """Remote offers no diff-empty check; unknown is not empty."""
    from web.api.worktree_backend import RemoteReviewWorktreeBackend

    backend = RemoteReviewWorktreeBackend(REMOTE, REPO, "n8n", "42")
    assert backend.diff_empty("main") is False


def test_review_local_delegates_to_facade(monkeypatch: pytest.MonkeyPatch) -> None:
    import web.api.worktree as wt
    import worktree_facade
    from web.api.worktree_backend import LocalReviewWorktreeBackend

    calls: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(
        worktree_facade,
        "worktree_is_dirty",
        lambda *a: calls.append(("dirty", a)) or True,
    )
    monkeypatch.setattr(
        worktree_facade,
        "worktree_diff_empty",
        lambda *a: calls.append(("diff", a)) or True,
    )
    monkeypatch.setattr(
        worktree_facade, "land_worktree", lambda *a: calls.append(("land", a)) or None
    )
    monkeypatch.setattr(
        wt, "base_repo_dirty", lambda *a: calls.append(("base_dirty", a)) or False
    )
    monkeypatch.setattr(
        wt, "base_repo_branch", lambda *a: calls.append(("base_branch", a)) or True
    )

    backend = LocalReviewWorktreeBackend(REPO, "trading", "42")
    assert backend.is_dirty() is True
    assert backend.diff_empty("main") is True
    assert backend.base_dirty() is False
    assert backend.base_on_branch("main") is True
    assert backend.land("main") is None

    assert [c[0] for c in calls] == [
        "dirty",
        "diff",
        "base_dirty",
        "base_branch",
        "land",
    ]
    assert calls[0][1] == (REPO, "trading", "42")
    assert calls[1][1] == (REPO, "trading", "42", "main")
    assert calls[2][1] == (REPO,)
    assert calls[3][1] == (REPO, "main")
    assert calls[4][1] == (REPO, "trading", "42", "main")


def test_review_remote_delegates_to_remote_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import remote_worktree
    from web.api.worktree_backend import RemoteReviewWorktreeBackend

    calls: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(
        remote_worktree,
        "worktree_is_dirty",
        lambda *a: calls.append(("dirty", a)) or True,
    )
    monkeypatch.setattr(
        remote_worktree,
        "base_repo_dirty",
        lambda *a: calls.append(("base_dirty", a)) or False,
    )
    monkeypatch.setattr(
        remote_worktree,
        "base_repo_branch",
        lambda *a: calls.append(("base_branch", a)) or True,
    )
    monkeypatch.setattr(
        remote_worktree, "land_worktree", lambda *a: calls.append(("land", a)) or None
    )

    backend = RemoteReviewWorktreeBackend(REMOTE, REPO, "n8n", "42")
    assert backend.is_dirty() is True
    assert backend.base_dirty() is False
    assert backend.base_on_branch("main") is True
    assert backend.land("main") is None

    assert [c[0] for c in calls] == ["dirty", "base_dirty", "base_branch", "land"]
    assert calls[0][1] == (REMOTE, REPO, "n8n", "42")
    assert calls[1][1] == (REMOTE, REPO)
    assert calls[2][1] == (REMOTE, REPO, "main")
    assert calls[3][1] == (REMOTE, REPO, "n8n", "42", "main")
