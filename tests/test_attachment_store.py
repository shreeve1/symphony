"""Unit tests for the local attachment store: name safety, size limits,
collision resistance, exclude idempotence, and containment."""

from __future__ import annotations

from pathlib import Path

import pytest

from web.api.attachments import (
    MAX_UPLOAD_BYTES,
    ensure_git_exclude,
    generate_stored_name,
    normalize_display_name,
    write_local,
    read_local,
    delete_local,
)


# ── normalize_display_name ────────────────────────────────


def test_normalize_plain_name() -> None:
    assert normalize_display_name("screenshot.png") == "screenshot.png"


def test_normalize_strips_traversal() -> None:
    assert normalize_display_name("../../../etc/passwd") == "passwd"


def test_normalize_strips_windows_traversal() -> None:
    assert normalize_display_name("..\\..\\Windows\\system32\\evil.exe") == "evil.exe"


def test_normalize_rejects_empty_after_strip() -> None:
    with pytest.raises(ValueError, match="empty"):
        normalize_display_name("   ")


def test_normalize_rejects_rootlike() -> None:
    with pytest.raises(ValueError, match="empty"):
        normalize_display_name("/")


# ── generate_stored_name ──────────────────────────────────


def test_stored_name_is_uuid_stem() -> None:
    name = generate_stored_name("log.txt")
    parts = name.split(".")
    assert len(parts) == 2
    assert len(parts[0]) == 32  # uuid4 hex
    assert parts[1] == "txt"


def test_stored_name_no_extension() -> None:
    name = generate_stored_name("README")
    # Path("README").suffix is "", no mimetype guess -> just uuid hex
    assert "." not in name
    assert len(name) == 32


def test_stored_name_collision_resistant() -> None:
    a = generate_stored_name("log.txt")
    b = generate_stored_name("log.txt")
    assert a != b


# ── write_local / read_local / delete_local ───────────────


def test_write_and_read_roundtrip(tmp_path: Path) -> None:
    content = b"hello attachment world"
    dest = write_local(tmp_path, 42, "abc123.dat", content)
    assert dest.exists()
    assert dest.read_bytes() == content
    assert read_local(tmp_path, 42, "abc123.dat") == content


def test_rejects_empty_content(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        write_local(tmp_path, 1, "x", b"")


def test_rejects_oversized_content(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exceeds"):
        write_local(tmp_path, 1, "x", b"a" * (MAX_UPLOAD_BYTES + 1))


def test_write_refuses_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes"):
        write_local(tmp_path, 1, "../evil.txt", b"x")


def test_write_refuses_absolute(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes"):
        write_local(tmp_path, 1, "/etc/passwd", b"x")


def test_write_never_outside_store(tmp_path: Path) -> None:
    dest = write_local(tmp_path, 7, "safe.dat", b"ok")
    # Must be under .symphony/attachments/7/
    assert ".symphony/attachments/7/" in str(dest)
    # Must not be symlink-slipped — parent containment already checked


def test_delete_missing_tolerated(tmp_path: Path) -> None:
    # should not raise
    delete_local(tmp_path, 99, "nonexistent.bin")


def test_delete_removes_existing(tmp_path: Path) -> None:
    dest = write_local(tmp_path, 1, "removeme.bin", b"gone")
    assert dest.exists()
    delete_local(tmp_path, 1, "removeme.bin")
    assert not dest.exists()


# ── ensure_git_exclude ────────────────────────────────────


def test_exclude_added_to_empty_exclude(tmp_path: Path) -> None:
    git_info = tmp_path / ".git" / "info"
    git_info.mkdir(parents=True)
    git_info.joinpath("exclude").write_text("# existing\n")
    assert ensure_git_exclude(tmp_path) is True
    content = git_info.joinpath("exclude").read_text()
    assert ".symphony/attachments/" in content


def test_exclude_idempotent(tmp_path: Path) -> None:
    git_info = tmp_path / ".git" / "info"
    git_info.mkdir(parents=True)
    # First call
    assert ensure_git_exclude(tmp_path) is True
    # Second call — already present
    assert ensure_git_exclude(tmp_path) is False
    # Only one line
    content = git_info.joinpath("exclude").read_text()
    assert content.count(".symphony/attachments/") == 1


def test_exclude_no_git_dir(tmp_path: Path) -> None:
    assert ensure_git_exclude(tmp_path) is False
