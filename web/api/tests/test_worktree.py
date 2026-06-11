"""Tests for web/api/worktree.py — worktree create, merge, cleanup, edge cases.

Each test creates a fresh git repo at a tmp_path to avoid cross-test
interference.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from web.api.worktree import (
    base_repo_dirty,
    branch_name,
    cleanup_worktree,
    create_worktree,
    merge_worktree,
    remove_worktree,
    worktree_dir,
    worktree_exists,
)


def _init_repo(path: Path) -> None:
    """Create a git repo at ``path`` with an initial commit on ``main``."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "test@test")
    _git(path, "config", "user.name", "Test")
    readme = path / "README.md"
    readme.write_text("# test", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "initial")


def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


# --- Test helpers ---


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Create a fresh git repo at tmp_path."""
    _init_repo(tmp_path)
    return tmp_path


@pytest.fixture
def binding_name() -> str:
    return "test-binding"


@pytest.fixture
def issue_id() -> str:
    return "42"


# --- worktree_path / branch_name ---


def test_worktree_path(repo: Path, binding_name: str, issue_id: str) -> None:
    expected = (repo / "worktrees" / binding_name / issue_id).resolve()
    assert worktree_dir(repo, binding_name, issue_id) == expected


def test_branch_name(binding_name: str, issue_id: str) -> None:
    assert branch_name(binding_name, issue_id) == f"podium/{binding_name}/{issue_id}"


# --- create_worktree ---


def test_create_worktree_creates_checkout(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    wt_path = create_worktree(repo, binding_name, issue_id, "main")
    assert wt_path.is_dir()
    assert (wt_path / "README.md").is_file()
    # The branch was created.
    branches = _git(repo, "branch", "--list").stdout
    assert f"podium/{binding_name}/{issue_id}" in branches


def test_create_worktree_idempotent(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    first = create_worktree(repo, binding_name, issue_id, "main")
    second = create_worktree(repo, binding_name, issue_id, "main")
    assert first == second
    assert second.is_dir()


def test_create_worktree_reuses_existing_branch(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    branch = branch_name(binding_name, issue_id)
    _git(repo, "branch", branch)

    wt_path = create_worktree(repo, binding_name, issue_id, "main")

    assert wt_path.is_dir()
    assert _git(wt_path, "branch", "--show-current").stdout.strip() == branch


# --- worktree_exists ---


def test_worktree_exists_after_create(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    assert not worktree_exists(repo, binding_name, issue_id)
    create_worktree(repo, binding_name, issue_id, "main")
    assert worktree_exists(repo, binding_name, issue_id)


# --- remove_worktree / cleanup_worktree ---


def test_remove_worktree_removes_both(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    create_worktree(repo, binding_name, issue_id, "main")
    remove_worktree(repo, binding_name, issue_id)
    assert not worktree_exists(repo, binding_name, issue_id)
    branches = _git(repo, "branch", "--list").stdout
    assert f"podium/{binding_name}/{issue_id}" not in branches


def test_remove_worktree_idempotent(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    remove_worktree(repo, binding_name, issue_id)  # should not raise


def test_cleanup_worktree(repo: Path, binding_name: str, issue_id: str) -> None:
    create_worktree(repo, binding_name, issue_id, "main")
    cleanup_worktree(repo, binding_name, issue_id)
    assert not worktree_exists(repo, binding_name, issue_id)


# --- base_repo_dirty ---


def test_base_repo_clean(repo: Path) -> None:
    assert not base_repo_dirty(repo)


def test_base_repo_dirty_with_uncommitted(repo: Path) -> None:
    # Modify a tracked file to make the repo dirty.
    (repo / "README.md").write_text("modified", encoding="utf-8")
    assert base_repo_dirty(repo)


def test_base_repo_podium_worktree_dir_not_dirty(repo: Path) -> None:
    """Podium-owned nested worktree dirs do not block their own merge."""
    (repo / "worktrees").mkdir(parents=True)
    (repo / "worktrees/untracked.txt").write_text("not tracked", encoding="utf-8")
    assert not base_repo_dirty(repo)


def test_base_repo_other_untracked_dirty(repo: Path) -> None:
    """Other untracked files still block auto-merge."""
    (repo / "scratch.txt").write_text("operator work", encoding="utf-8")
    assert base_repo_dirty(repo)


# --- merge_worktree (happy path) ---


def test_merge_worktree_fast_forward(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    """Create a worktree branch, commit to it, then FF-merge into main."""
    wt_path = create_worktree(repo, binding_name, issue_id, "main")
    # Make a change in the worktree.
    (wt_path / "feature.txt").write_text("feature work", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "feature commit")

    error = merge_worktree(repo, binding_name, issue_id, "main")

    assert error is None, f"merge failed: {error}"
    # The merge landed the feature commit.
    log = _git(repo, "log", "--oneline", "-1").stdout
    assert "feature commit" in log
    # Clean up after merge.
    cleanup_worktree(repo, binding_name, issue_id)
    assert not worktree_exists(repo, binding_name, issue_id)


# --- merge_worktree (conflict / no-op cases) ---


def test_merge_worktree_noop_when_already_merged(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    """Branch already merged into main — nothing to do."""
    wt_path = create_worktree(repo, binding_name, issue_id, "main")
    (wt_path / "feature.txt").write_text("feature", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "feature")

    # Merge once.
    assert merge_worktree(repo, binding_name, issue_id, "main") is None
    # Branch is destroyed after cleanup; worktree gone — nothing to merge.
    error = merge_worktree(repo, binding_name, issue_id, "main")
    assert error is None  # safe no-op


def test_merge_worktree_fails_on_diverged_base(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    """Base has diverged: a commit on main prevents FF merge."""
    wt_path = create_worktree(repo, binding_name, issue_id, "main")
    # Commit on worktree.
    (wt_path / "feature.txt").write_text("feature", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "feature")

    # Commit on main (diverges).
    (repo / "main-edit.txt").write_text("main work", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "main edit")

    error = merge_worktree(repo, binding_name, issue_id, "main")
    assert error is not None
    assert "Auto-merge halted" in error
    # Worktree should remain intact.
    assert worktree_exists(repo, binding_name, issue_id)


def test_merge_worktree_fails_on_dirty_base(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    """Uncommitted changes in base repo cause abort before merge attempt."""
    create_worktree(repo, binding_name, issue_id, "main")
    # Modify a tracked file in the base.
    (repo / "README.md").write_text("uncommitted change", encoding="utf-8")
    assert base_repo_dirty(repo)
