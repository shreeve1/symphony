"""Safe checkout-local attachment store.

Constants, display-name normalization, collision-resistant stored-name
generation, local filesystem operations, and idempotent .git/info/exclude
management.  No API routing — that lives in a future phase.
"""

from __future__ import annotations

import contextlib
import mimetypes
import shlex
import subprocess
import uuid
from pathlib import Path

from config import RemotePolicy
from ssh_support import ssh_base_args

# Directory under the binding repo checkout where all attachments live,
# keyed by issue_id:  .symphony/attachments/<issue_id>/<stored_name>
STORAGE_DIR = ".symphony/attachments"

# Reject uploads larger than this.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MiB

GIT_EXCLUDE_LINE = ".symphony/attachments/\n"


def normalize_display_name(raw: str) -> str:
    """Strip directory separators so a malicious display name cannot escape the
    attachment directory.  Returns the leaf name only; empty after stripping
    raises ValueError."""
    # Also normalise Windows backslash separators; Path().name strips only /.
    name = Path(raw.replace("\\", "/")).name.strip()
    if not name:
        raise ValueError("display_name is empty or path-like")
    return name


def generate_stored_name(display_name: str) -> str:
    """Collision-resistant stored filename: uuid4 stem, original suffix if
    detectible, otherwise keep the display name as-is."""
    suffix = Path(display_name).suffix
    # mimetypes fallback: if no suffix, try to guess from MIME patterns
    if not suffix:
        guess, _ = mimetypes.guess_type(display_name)
        if guess:
            ext = mimetypes.guess_extension(guess)
            if ext:
                suffix = ext
    return f"{uuid.uuid4().hex}{suffix}"


def _resolve_path(repo_path: Path, issue_id: int, stored_name: str) -> Path:
    """Resolve an attachment path strictly under STORAGE_DIR/<issue_id>/.
    Raises ValueError if stored_name would escape."""
    base = (repo_path / STORAGE_DIR / str(issue_id)).resolve()
    resolved = (base / stored_name).resolve()
    if base not in resolved.parents and resolved != base:
        raise ValueError(f"stored_name escapes attachment dir: {stored_name}")
    return resolved


def write_local(
    repo_path: Path,
    issue_id: int,
    stored_name: str,
    content: bytes,
) -> Path:
    """Write attachment bytes to the local checkout and return the absolute
    path.  Creates parent directories.  Never writes outside the store."""
    if not content:
        raise ValueError("attachment content is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"attachment size {len(content)} exceeds {MAX_UPLOAD_BYTES} byte limit"
        )
    dest = _resolve_path(repo_path, issue_id, stored_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return dest


def read_local(repo_path: Path, issue_id: int, stored_name: str) -> bytes:
    """Read attachment bytes from the local checkout."""
    return _resolve_path(repo_path, issue_id, stored_name).read_bytes()


def delete_local(repo_path: Path, issue_id: int, stored_name: str) -> None:
    """Delete attachment file.  Missing file is tolerated (best-effort)."""
    path = _resolve_path(repo_path, issue_id, stored_name)
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


def ensure_git_exclude(repo_path: Path) -> bool:
    """Append `.symphony/attachments/` to `.git/info/exclude` exactly once.
    Returns True if the line was added, False if already present or .git/info
    does not exist."""
    exclude_path = repo_path / ".git" / "info" / "exclude"
    if not (repo_path / ".git").is_dir():
        return False
    try:
        current = exclude_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        current = ""
    if GIT_EXCLUDE_LINE in current:
        return False
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    exclude_path.write_text(
        current.rstrip("\n") + "\n" + GIT_EXCLUDE_LINE,
        encoding="utf-8",
    )
    return True


# ── Remote (SSH) attachment transport ─────────────────────


def _remote_path(remote_repo: Path, issue_id: int, stored_name: str) -> Path:
    """Resolve the remote attachment path.  Same containment check as local."""
    return _resolve_path(remote_repo, issue_id, stored_name)


def write_remote(
    remote: RemotePolicy,
    repo_path: Path,
    issue_id: int,
    stored_name: str,
    content: bytes,
) -> Path:
    """Write attachment bytes over SSH to the remote checkout.

    Creates parent directories with ``mkdir -p`` then writes ``content``
    via ``cat > path`` with binary stdin.
    """
    if not content:
        raise ValueError("attachment content is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"attachment size {len(content)} exceeds {MAX_UPLOAD_BYTES} byte limit"
        )
    dest = _remote_path(repo_path, issue_id, stored_name)
    dest_q = shlex.quote(str(dest))
    dest_dir_q = shlex.quote(str(dest.parent))
    cmd = f"mkdir -p {dest_dir_q} && cat > {dest_q}"
    subprocess.run(
        ssh_base_args(remote) + [cmd],
        input=content,
        capture_output=True,
        check=True,
        timeout=30,
    )
    return dest


def read_remote(
    remote: RemotePolicy,
    repo_path: Path,
    issue_id: int,
    stored_name: str,
) -> bytes:
    """Read attachment bytes over SSH from the remote checkout."""
    path = _remote_path(repo_path, issue_id, stored_name)
    result = subprocess.run(
        ssh_base_args(remote) + [f"cat {shlex.quote(str(path))}"],
        capture_output=True,
        check=True,
        timeout=30,
    )
    return result.stdout


def delete_remote(
    remote: RemotePolicy,
    repo_path: Path,
    issue_id: int,
    stored_name: str,
) -> None:
    """Delete attachment file over SSH.  Missing file is tolerated (best-effort)."""
    path = _remote_path(repo_path, issue_id, stored_name)
    subprocess.run(
        ssh_base_args(remote) + [f"rm -f {shlex.quote(str(path))}"],
        capture_output=True,
        timeout=30,
    )
