"""Tests for web/api/worktree.py — worktree create, merge, cleanup, edge cases.

Each test creates a fresh git repo at a tmp_path to avoid cross-test
interference.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

import web.api.worktree as worktree_module
from web.api.worktree import (
    base_repo_branch,
    base_repo_dirty,
    branch_name,
    cleanup_worktree,
    create_worktree,
    land_worktree,
    merge_worktree,
    merge_worktree_preserving_base_wip,
    remove_worktree,
    resolve_github_repo,
    worktree_diff_empty,
    worktree_dir,
    worktree_exists,
    worktree_is_dirty,
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


def test_land_worktree_merges_and_cleans_up(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    wt_path = create_worktree(repo, binding_name, issue_id, "main")
    (wt_path / "feature.txt").write_text("feature work", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "feature commit")

    assert land_worktree(repo, binding_name, issue_id, "main") is None

    assert "feature commit" in _git(repo, "log", "--oneline", "-1").stdout
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

    # Modified or staged files starting with worktrees/ are also excused
    # We can't easily trigger a real porcelain staged/modified on temporary repo fixture without git operations,
    # but we can mock or verify path-anchoring.
    # To test path-anchoring of nested/false-positive paths:
    (repo / "docs/worktrees").mkdir(parents=True, exist_ok=True)
    (repo / "docs/worktrees/untracked.txt").write_text("dirty nested", encoding="utf-8")
    assert base_repo_dirty(repo)


def test_base_repo_other_untracked_dirty(repo: Path) -> None:
    """Other untracked files still block auto-merge."""
    (repo / "scratch.txt").write_text("operator work", encoding="utf-8")
    assert base_repo_dirty(repo)


# --- base_repo_branch ---


def test_base_repo_branch_matches_default_main(repo: Path) -> None:
    """Issue #10 / ADR-0041: fresh repo is on ``main``; the helper returns True."""
    assert base_repo_branch(repo, "main")


def test_base_repo_branch_mismatch(repo: Path) -> None:
    """Helper returns False when HEAD is on a different branch than expected."""
    _git(repo, "checkout", "-b", "feature")
    assert not base_repo_branch(repo, "main")
    assert base_repo_branch(repo, "feature")


def test_base_repo_branch_empty_returns_true(repo: Path) -> None:
    """Empty ``base_branch`` is opt-in: callers without a pinned base do not
    false-block. The gate is intentionally permissive when the target is
    unknown.
    """
    assert base_repo_branch(repo, "")


def test_base_repo_branch_non_git_dir(tmp_path: Path) -> None:
    """Non-git directories return False (not on the requested branch)."""
    non_repo = tmp_path / "not-a-repo"
    non_repo.mkdir()
    assert not base_repo_branch(non_repo, "main")


def test_base_repo_branch_detached_head_fails_closed(repo: Path) -> None:
    """Detached HEAD reports ``HEAD`` (not the branch name); the helper
    returns False unless ``base_branch`` is literally ``HEAD``. Guards
    against closing the Issue to done when the agent committed in detached
    state (a degenerate but plausible base-checkout state).
    """
    _git(repo, "checkout", "--detach")
    assert not base_repo_branch(repo, "main")


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


def test_merge_worktree_fast_forward_does_not_rebase(
    repo: Path,
    binding_name: str,
    issue_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Already-FF branches do not pay the rebase path."""
    wt_path = create_worktree(repo, binding_name, issue_id, "main")
    (wt_path / "feature.txt").write_text("feature work", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "feature commit")

    rebase_calls: list[list[str]] = []
    real_run = worktree_module.subprocess.run

    def recording_run(cmd: list[str], *args: Any, **kwargs: Any) -> Any:
        if "rebase" in cmd:
            rebase_calls.append(cmd)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(worktree_module.subprocess, "run", recording_run)

    assert merge_worktree(repo, binding_name, issue_id, "main") is None
    assert rebase_calls == []


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
    # Second merge is already up to date and remains a safe no-op.
    error = merge_worktree(repo, binding_name, issue_id, "main")
    assert error is None


def test_merge_worktree_rebases_diverged_base(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    """Base moved with no conflict: rebase the worktree and retry FF merge."""
    wt_path = create_worktree(repo, binding_name, issue_id, "main")
    # Commit on worktree.
    (wt_path / "feature.txt").write_text("feature", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "feature")

    # Commit on main (diverges, but does not conflict).
    (repo / "main-edit.txt").write_text("main work", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "main edit")

    error = merge_worktree(repo, binding_name, issue_id, "main")
    assert error is None
    assert (repo / "feature.txt").read_text(encoding="utf-8") == "feature"
    assert (repo / "main-edit.txt").read_text(encoding="utf-8") == "main work"
    cleanup_worktree(repo, binding_name, issue_id)
    assert not worktree_exists(repo, binding_name, issue_id)


def test_merge_preserving_base_wip_restores_non_conflicting_dirty_files(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    wt_path = create_worktree(repo, binding_name, issue_id, "main")
    (wt_path / "feature.txt").write_text("feature work", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "feature commit")

    (repo / "operator.txt").write_text("operator WIP", encoding="utf-8")

    error = merge_worktree_preserving_base_wip(repo, binding_name, issue_id, "main")

    assert error is None
    assert (repo / "feature.txt").read_text(encoding="utf-8") == "feature work"
    assert (repo / "operator.txt").read_text(encoding="utf-8") == "operator WIP"
    assert "?? operator.txt" in _git(repo, "status", "--porcelain").stdout
    assert _git(repo, "stash", "list").stdout == ""


def test_merge_preserving_base_wip_issue_wins_conflicting_file(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    wt_path = create_worktree(repo, binding_name, issue_id, "main")
    (wt_path / "README.md").write_text("issue version", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "issue edit")

    (repo / "README.md").write_text("operator WIP", encoding="utf-8")

    error = merge_worktree_preserving_base_wip(repo, binding_name, issue_id, "main")

    assert error is None
    assert (repo / "README.md").read_text(encoding="utf-8") == "issue version"
    assert not base_repo_dirty(repo)
    assert _git(repo, "stash", "list").stdout == ""


def test_merge_worktree_rebase_conflict_blocks_cleanly(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    """Conflicting rebase aborts and leaves the worktree for inspection."""
    wt_path = create_worktree(repo, binding_name, issue_id, "main")
    (wt_path / "README.md").write_text("feature edit", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "feature")

    (repo / "README.md").write_text("main edit", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "main edit")

    error = merge_worktree(repo, binding_name, issue_id, "main")

    assert error is not None
    assert "Auto-merge halted" in error
    assert worktree_exists(repo, binding_name, issue_id)
    assert _git(repo, "branch", "--show-current").stdout.strip() == "main"
    assert (repo / "README.md").read_text(encoding="utf-8") == "main edit"
    assert not base_repo_dirty(repo)
    assert _git(wt_path, "status", "--porcelain").stdout == ""


def test_base_repo_dirty_detects_tracked_edits(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    """Dirty-base detection is the guard used by the API before merge."""
    create_worktree(repo, binding_name, issue_id, "main")
    # Modify a tracked file in the base.
    (repo / "README.md").write_text("uncommitted change", encoding="utf-8")
    assert base_repo_dirty(repo)


# --- worktree_is_dirty (ADR-0014) ---


def test_worktree_is_dirty_clean_returns_false(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    """A freshly created worktree with no edits is clean."""
    create_worktree(repo, binding_name, issue_id, "main")
    assert not worktree_is_dirty(repo, binding_name, issue_id)


def test_worktree_is_dirty_tracked_modification(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    """A modified tracked file inside the worktree is dirty."""
    wt_path = create_worktree(repo, binding_name, issue_id, "main")
    (wt_path / "README.md").write_text("modified", encoding="utf-8")
    assert worktree_is_dirty(repo, binding_name, issue_id)


def test_worktree_is_dirty_untracked_file(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    """An untracked file inside the worktree is real agent output → dirty.

    Unlike base_repo_dirty, untracked files are NOT excused here: a leaf
    worktree has no nested Podium worktrees.
    """
    wt_path = create_worktree(repo, binding_name, issue_id, "main")
    (wt_path / "feature.txt").write_text("agent work", encoding="utf-8")
    assert worktree_is_dirty(repo, binding_name, issue_id)


def test_worktree_is_dirty_absent_worktree_returns_false(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    """No worktree directory → not dirty (nothing to lose)."""
    assert not worktree_is_dirty(repo, binding_name, issue_id)


def test_worktree_is_dirty_clean_after_commit(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    """Committed work in the worktree leaves it clean (Case 1, not re-dispatch)."""
    wt_path = create_worktree(repo, binding_name, issue_id, "main")
    (wt_path / "feature.txt").write_text("agent work", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "agent change")
    assert not worktree_is_dirty(repo, binding_name, issue_id)


# --- worktree_diff_empty (ADR-0024) ---


def test_worktree_diff_empty_clean_branch_returns_true(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    create_worktree(repo, binding_name, issue_id, "main")
    assert worktree_diff_empty(repo, binding_name, issue_id, "main")


def test_worktree_diff_empty_committed_change_returns_false(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    wt_path = create_worktree(repo, binding_name, issue_id, "main")
    (wt_path / "feature.txt").write_text("agent work", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "agent change")
    assert not worktree_diff_empty(repo, binding_name, issue_id, "main")


def test_worktree_diff_empty_absent_worktree_returns_false(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    assert not worktree_diff_empty(repo, binding_name, issue_id, "main")


def test_worktree_diff_empty_missing_branch_returns_false(
    repo: Path, binding_name: str, issue_id: str
) -> None:
    worktree_dir(repo, binding_name, issue_id).mkdir(parents=True)
    assert not worktree_diff_empty(repo, binding_name, issue_id, "main")


# --- resolve_github_repo (ADR-0042 section 1) ---


def test_resolve_github_repo_ssh_alias(repo: Path) -> None:
    """ADR-0042: must handle the `github-personal` alias from CLAUDE.md."""
    _git(
        repo,
        "remote",
        "add",
        "origin",
        "git@github-personal:shreeve1/symphony.git",
    )
    assert resolve_github_repo(repo) == ("shreeve1", "symphony")


def test_resolve_github_repo_ssh_default_host(repo: Path) -> None:
    """Plain `github.com` SSH form is also accepted."""
    _git(repo, "remote", "add", "origin", "git@github.com:owner/repo.git")
    assert resolve_github_repo(repo) == ("owner", "repo")


def test_resolve_github_repo_https(repo: Path) -> None:
    """HTTPS GitHub URL (with and without .git suffix)."""
    _git(repo, "remote", "add", "origin", "https://github.com/owner/repo.git")
    assert resolve_github_repo(repo) == ("owner", "repo")

    _git(repo, "remote", "set-url", "origin", "https://github.com/owner/repo")
    assert resolve_github_repo(repo) == ("owner", "repo")


def test_resolve_github_repo_https_with_userinfo(repo: Path) -> None:
    """Some `gh`/git configs include a `user@` userinfo prefix."""
    _git(
        repo,
        "remote",
        "add",
        "origin",
        "https://gh-token@github.com/owner/repo.git",
    )
    assert resolve_github_repo(repo) == ("owner", "repo")


def test_resolve_github_repo_non_github_host(repo: Path) -> None:
    """HTTPS to a non-GitHub host returns None (binding gets no Sync button).

    Note: SSH aliases are operator-controlled and not validated by host name —
    any `git@host:owner/repo` shape is accepted per ADR-0042 section 1.
    """
    _git(repo, "remote", "add", "origin", "https://gitlab.com/owner/repo.git")
    assert resolve_github_repo(repo) is None


def test_resolve_github_repo_missing_remote(repo: Path) -> None:
    """A repo with no `origin` remote returns None."""
    assert resolve_github_repo(repo) is None


def test_resolve_github_repo_non_git_dir(tmp_path: Path) -> None:
    """Non-git directories return None rather than raising."""
    non_repo = tmp_path / "not-a-repo"
    non_repo.mkdir()
    assert resolve_github_repo(non_repo) is None
