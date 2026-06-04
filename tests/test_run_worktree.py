"""Tests for run_worktree helpers (list_worktrees, tmux, run_id parsing)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from run_worktree import (
    _run_id_from_identifier,
    _run_id_from_worktree_path,
    list_worktrees,
    tmux_session_name,
)


def _init_tmp_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Seed", "-c", "user.email=seed@test",
         "commit", "--allow-empty", "-q", "-m", "seed"],
        cwd=repo, check=True,
    )


def test_run_id_from_identifier_deterministic() -> None:
    assert _run_id_from_identifier("HOM-1") == _run_id_from_identifier("HOM-1")
    assert _run_id_from_identifier("hOM-1") == _run_id_from_identifier("HOM-1")  # case-insensitive
    assert len(_run_id_from_identifier("HOM-1")) == 8


def test_run_id_from_worktree_path_extracts_run_id_in_worktrees_dir() -> None:
    repo = Path("/repo")
    wt_path = repo / "worktrees" / "run-abc12345"
    result = _run_id_from_worktree_path(repo, wt_path)
    assert result == "abc12345"


def test_run_id_from_worktree_path_extracts_run_id_from_external_worktrees_root() -> None:
    repo = Path("/repo")
    # Worktree outside the homelab repo, e.g. at worktrees_root/run-abc12345
    wt_path = Path("/some/path/run-abc12345")
    result = _run_id_from_worktree_path(repo, wt_path)
    assert result == "abc12345"


def test_run_id_from_worktree_path_returns_none_for_non_run_prefix() -> None:
    repo = Path("/repo")
    wt_path = repo / "worktrees" / "not-a-run-abc12345"
    result = _run_id_from_worktree_path(repo, wt_path)
    assert result is None


def test_tmux_session_name() -> None:
    assert tmux_session_name("abc12345") == "symphony-abc12345"