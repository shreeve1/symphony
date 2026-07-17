"""Tests for remote (SSH) attachment transport.

Asserts SSH command shape and byte input without requiring a live remote host.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import RemotePolicy
from web.api.attachments import (
    MAX_UPLOAD_BYTES,
    delete_remote,
    read_remote,
    write_remote,
)


def _remote() -> RemotePolicy:
    return RemotePolicy(host="buildbox", user="symphony", identity="/key")


# ── write_remote ──────────────────────────────────────────


def test_write_remote_mkdir_and_cat(tmp_path: Path) -> None:
    """Remote write pipes bytes through mkdir -p && cat > path."""
    remote = _remote()
    content = b"hello remote"
    mock_run = MagicMock()

    with patch.object(subprocess, "run", mock_run):
        dest = write_remote(remote, tmp_path, 7, "abc.dat", content)

    mock_run.assert_called_once()
    (args,) = mock_run.call_args[0]
    cmd = args[-1]
    assert cmd.startswith("mkdir -p ")
    assert " && cat > " in cmd
    assert "abc.dat" in cmd
    assert ".symphony/attachments/7/" in cmd
    assert mock_run.call_args[1]["input"] == content
    assert dest.suffix == ".dat"


def test_write_remote_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        write_remote(_remote(), Path("/"), 1, "x", b"")


def test_write_remote_rejects_oversized() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        write_remote(_remote(), Path("/"), 1, "x", b"a" * (MAX_UPLOAD_BYTES + 1))


def test_write_remote_uses_binary_input() -> None:
    """Binary content survives SSH pipe without text encoding."""
    remote = _remote()
    content = bytes(range(256))  # includes non-utf8
    mock_run = MagicMock()

    with patch.object(subprocess, "run", mock_run):
        write_remote(remote, Path("/srv/bindings/myproject"), 42, "f.bin", content)

    assert mock_run.call_args[1]["input"] == content


# ── read_remote ───────────────────────────────────────────


def test_read_remote_cat() -> None:
    """Remote read uses ``cat`` with quoted path."""
    remote = _remote()
    expected = b"fetched bytes"
    mock_run = MagicMock()
    mock_run.return_value = MagicMock(stdout=expected)

    with patch.object(subprocess, "run", mock_run):
        result = read_remote(remote, Path("/srv/repo"), 3, "abc.dat")

    mock_run.assert_called_once()
    (args,) = mock_run.call_args[0]
    cmd = args[-1]
    assert cmd.startswith("cat ")
    assert "abc.dat" in cmd
    assert ".symphony/attachments/3/" in cmd
    assert result == expected


def test_read_remote_capture_is_binary() -> None:
    """stdout is captured as raw bytes (no text=True)."""
    remote = _remote()
    mock_run = MagicMock()
    mock_run.return_value = MagicMock(stdout=b"\xff\xfe")

    with patch.object(subprocess, "run", mock_run):
        result = read_remote(remote, Path("/srv/repo"), 1, "bin.dat")

    assert result == b"\xff\xfe"
    # Verify subprocess.run doesn't get text=True
    assert mock_run.call_args[1].get("text") is not True


# ── delete_remote ─────────────────────────────────────────


def test_delete_remote_rm_f() -> None:
    """Remote delete uses ``rm -f`` with quoted path."""
    remote = _remote()
    mock_run = MagicMock()

    with patch.object(subprocess, "run", mock_run):
        delete_remote(remote, Path("/srv/repo"), 5, "del.me")

    mock_run.assert_called_once()
    (args,) = mock_run.call_args[0]
    cmd = args[-1]
    assert cmd.startswith("rm -f ")
    assert "del.me" in cmd
    assert ".symphony/attachments/5/" in cmd


def test_delete_remote_checks_ssh_failure() -> None:
    """A transport failure must preserve attachment metadata for retry."""
    mock_run = MagicMock()

    with patch.object(subprocess, "run", mock_run):
        delete_remote(_remote(), Path("/srv/repo"), 9, "ghost.bin")

    assert mock_run.call_args.kwargs["check"] is True


def test_delete_remote_uses_ssh_args() -> None:
    """Verify SSH base args include identity, user@host."""
    remote = _remote()
    mock_run = MagicMock()

    with patch.object(subprocess, "run", mock_run):
        delete_remote(remote, Path("/srv/repo"), 2, "x")

    (args,) = mock_run.call_args[0]
    ssh_args = args[:-1]  # everything except the command
    assert "-i" in ssh_args
    assert "/key" in ssh_args
    assert "symphony@buildbox" in ssh_args
