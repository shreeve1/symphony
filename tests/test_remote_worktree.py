from __future__ import annotations

import subprocess
from pathlib import Path

import remote_worktree  # type: ignore[import-not-found]
from config import RemotePolicy


def _completed(command: list[str], returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(command, returncode, stdout="", stderr="")


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
