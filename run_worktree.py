"""Git worktree lifecycle for per-Run isolation.

Each Run gets its own worktree + branch created from the binding's base branch.
This makes same-repo parallelism safe by isolating edits, staging, and branch
state to an ephemeral tree that is torn down after the Verdict is reconciled.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path

from config import SymphonyConfig


LOGGER = logging.getLogger(__name__)

# Default base branch when no explicit binding is configured.
DEFAULT_BASE_BRANCH = "HEAD"


def _run_id_from_identifier(identifier: str) -> str:
    """Derive a short, URL-safe run ID from an issue identifier.

    The ID is deterministic so durable signals (worktree dirs, branches, tmux
    sessions) can be matched back to a Run without storing an in-memory map.
    """

    normalized = identifier.strip().lower()
    digest = hashlib.sha256(normalized.encode()).hexdigest()
    return digest[:8]


def worktree_path(config: SymphonyConfig, run_id: str) -> Path:
    """Absolute path for the Run's worktree directory."""

    assert config.worktrees_root is not None
    return config.worktrees_root / f"run-{run_id}"


def worktree_branch(run_id: str) -> str:
    """Branch name for the Run's worktree."""

    return f"symphony/run-{run_id}"


def tmux_session_name(run_id: str) -> str:
    """Tmux session name for the Run's worktree."""

    return f"symphony-{run_id}"


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result


def _git_checked(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Like _git but raises RuntimeError on non-zero exit."""

    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)!r} failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return result


class WorktreeError(RuntimeError):
    """Raised when a worktree operation fails."""


def create_worktree(
    config: SymphonyConfig,
    run_id: str,
    base_branch: str | None = None,
) -> Path:
    """Create a new worktree and branch for a Run.

    Creates ``config.worktrees_root / run-<run_id>`` as a git worktree on a
    new branch ``symphony/run-<run_id>`` branched from the configured base
    branch (or the current HEAD when no base branch is configured). Returns
    the absolute worktree path.

    Raises WorktreeError if the worktree already exists or any git command fails.
    """

    wt_path = worktree_path(config, run_id)
    branch = worktree_branch(run_id)
    base_ref = base_branch or DEFAULT_BASE_BRANCH

    # Check if worktree already exists (crash-recovery scenario).
    try:
        _git("worktree", "list", "--porcelain", cwd=config.homelab_repo_path)
    except subprocess.CalledProcessError:
        pass  # listed below

    list_result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=config.homelab_repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    existing_paths: set[str] = set()
    for line in list_result.stdout.splitlines():
        if line.startswith("worktree "):
            existing_paths.add(line[len("worktree "):].strip())

    if str(wt_path) in existing_paths:
        raise WorktreeError(f"Worktree already exists at {wt_path}")

    wt_path.parent.mkdir(parents=True, exist_ok=True)

    branch_exists = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=config.homelab_repo_path,
        check=False,
    ).returncode == 0

    add_args = ["worktree", "add", str(wt_path), branch]
    if not branch_exists:
        add_args = ["worktree", "add", "-b", branch, str(wt_path), base_ref]

    try:
        _git_checked(*add_args, cwd=config.homelab_repo_path)
    except RuntimeError as exc:
        raise WorktreeError(f"git worktree add failed: {exc}") from exc

    LOGGER.info(
        "worktree_created run_id=%s path=%s branch=%s",
        run_id, wt_path, branch,
    )
    return wt_path


def remove_worktree(config: SymphonyConfig, run_id: str) -> None:
    """Remove the Run's worktree while keeping its branch.

    This is the canonical cleanup path called after Verdict reconciliation
    and on all crash/timeout cleanup paths so no orphaned worktree is left
    behind. The branch is retained because it contains the run's committed
    changes for later landing. Silently succeeds if the worktree does not exist.
    """

    wt_path = worktree_path(config, run_id)
    branch = worktree_branch(run_id)

    # Check worktree exists.
    list_result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=config.homelab_repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if str(wt_path) not in list_result.stdout:
        LOGGER.debug("worktree_already_gone run_id=%s path=%s", run_id, wt_path)
        return

    # Remove the worktree first.
    try:
        _git_checked("worktree", "remove", "--force", str(wt_path), cwd=config.homelab_repo_path)
    except RuntimeError as exc:
        LOGGER.warning("worktree_remove_failed run_id=%s path=%s error=%s", run_id, wt_path, exc)
        # Try to prune anyway to clean up git's bookkeeping.
        try:
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=config.homelab_repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            pass
        raise WorktreeError(f"git worktree remove failed: {exc}") from exc

    LOGGER.info("worktree_removed run_id=%s path=%s branch=%s", run_id, wt_path, branch)


def remove_worktree_if_exists(config: SymphonyConfig, run_id: str) -> None:
    """Remove the Run's worktree, suppressing WorktreeError on missing worktree.

    Use this on crash/timeout paths where the worktree may or may not have been
    created before the failure.
    """

    try:
        remove_worktree(config, run_id)
    except WorktreeError as exc:
        LOGGER.debug("worktree_cleanup_ignored run_id=%s error=%s", run_id, exc)
