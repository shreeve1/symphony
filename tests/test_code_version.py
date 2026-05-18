"""Tests for ``code_version.resolve_code_sha``."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import code_version


def test_resolve_code_sha_returns_short_sha_for_this_repo() -> None:
    sha = code_version.resolve_code_sha()
    assert sha != code_version.UNKNOWN
    assert 7 <= len(sha) <= 40
    assert all(c in "0123456789abcdef" for c in sha)


def test_resolve_code_sha_returns_unknown_for_non_git_dir(tmp_path: Path) -> None:
    sha = code_version.resolve_code_sha(tmp_path)
    assert sha == code_version.UNKNOWN


def test_resolve_code_sha_handles_missing_git_binary() -> None:
    def boom(*args, **kwargs):
        raise FileNotFoundError("git")

    with patch.object(subprocess, "run", side_effect=boom):
        assert code_version.resolve_code_sha() == code_version.UNKNOWN


def test_resolve_code_sha_handles_timeout() -> None:
    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=5)

    with patch.object(subprocess, "run", side_effect=slow):
        assert code_version.resolve_code_sha() == code_version.UNKNOWN
