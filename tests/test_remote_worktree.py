from __future__ import annotations

import subprocess
from pathlib import Path

import remote_worktree  # type: ignore[import-not-found]
from config import RemotePolicy


def _completed(
    command: list[str],
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        command, returncode, stdout=stdout, stderr=stderr
    )


def test_create_worktree_uses_remote_git_commands() -> None:
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return _completed(command)

    path = remote_worktree.create_worktree(
        RemotePolicy(host="host", user="user"),
        Path("/repo"),
        "n8n",
        "42",
        "main",
        run_func=fake_run,
    )

    assert path == Path("/repo/worktrees/n8n/42")
    assert calls[0][:2] == ["ssh", "-o"]
    assert "git -C /repo worktree add" in calls[0][-1]
    assert "podium/n8n/42" in calls[0][-1]


def test_dirty_false_when_remote_worktree_missing() -> None:
    def fake_run(command, **kwargs):
        return _completed(command, 1 if "test -d" in command[-1] else 0)

    assert not remote_worktree.worktree_is_dirty(
        RemotePolicy(host="host", user="user"),
        Path("/repo"),
        "n8n",
        "42",
        run_func=fake_run,
    )


def test_land_worktree_removes_after_success() -> None:
    calls: list[str] = []

    def fake_run(command, **kwargs):
        calls.append(command[-1])
        return _completed(command)

    error = remote_worktree.land_worktree(
        RemotePolicy(host="host", user="user"),
        Path("/repo"),
        "n8n",
        "42",
        "main",
        run_func=fake_run,
    )

    assert error is None
    assert any("merge --ff-only podium/n8n/42" in call for call in calls)
    assert any(
        "worktree remove --force /repo/worktrees/n8n/42" in call for call in calls
    )


def test_base_repo_branch_matches_remote_head() -> None:
    """Issue #10: ``base_repo_branch`` returns True when remote HEAD matches."""
    captured: list[str] = []

    def fake_run(command, **kwargs):
        captured.append(command[-1])
        # Last call is the rev-parse; report ``main`` as the current branch.
        if "rev-parse" in command[-1]:
            return _completed(command, stdout="main\n")
        return _completed(command)

    assert remote_worktree.base_repo_branch(
        RemotePolicy(host="host", user="user"),
        Path("/repo"),
        "main",
        run_func=fake_run,
    )
    assert any("rev-parse --abbrev-ref HEAD" in call for call in captured)


def test_base_repo_branch_mismatch_remote() -> None:
    """Returns False when remote HEAD is on a different branch."""

    def fake_run(command, **kwargs):
        if "rev-parse" in command[-1]:
            return _completed(command, stdout="feature\n")
        return _completed(command)

    assert not remote_worktree.base_repo_branch(
        RemotePolicy(host="host", user="user"),
        Path("/repo"),
        "main",
        run_func=fake_run,
    )


def test_base_repo_branch_empty_returns_true() -> None:
    """Empty ``base_branch`` is opt-in: no SSH call is made, returns True."""

    def fake_run(command, **kwargs):
        raise AssertionError("should not invoke remote when base_branch is empty")

    assert remote_worktree.base_repo_branch(
        RemotePolicy(host="host", user="user"),
        Path("/repo"),
        "",
        run_func=fake_run,
    )


def test_base_repo_branch_detached_head_fails_closed() -> None:
    """A detached HEAD reports ``HEAD`` (not the branch name); the helper
    returns False unless ``base_branch`` is literally ``HEAD``. This guards
    against closing the Issue to done when the agent committed in detached
    state (a degenerate but plausible base-checkout state).
    """

    def fake_run(command, **kwargs):
        if "rev-parse" in command[-1]:
            return _completed(command, stdout="HEAD\n")
        return _completed(command)

    assert not remote_worktree.base_repo_branch(
        RemotePolicy(host="host", user="user"),
        Path("/repo"),
        "main",
        run_func=fake_run,
    )
