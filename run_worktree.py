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


def list_worktrees(homelab_repo_path: Path) -> list[tuple[Path, str]]:
    """List all worktrees for the homelab repo.

    Returns a list of (worktree_path, branch) tuples. The homelab shared checkout
    itself is excluded so only per-run worktrees are returned.
    """
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=homelab_repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []

    worktrees: list[tuple[Path, str]] = []
    lines = result.stdout.splitlines()
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if line.startswith("worktree "):
            wt_path = Path(line[len("worktree "):].strip())
            branch = ""
            # Skip the commit hash line if present.
            idx += 1
            while idx < len(lines):
                next_line = lines[idx].strip()
                if next_line.startswith("worktree "):
                    break
                if next_line.startswith("branch "):
                    branch = next_line[len("branch "):].strip()
                idx += 1
            # Exclude the shared checkout itself.
            if wt_path.resolve() != homelab_repo_path.resolve():
                worktrees.append((wt_path, branch))
        else:
            idx += 1
    return worktrees


def _run_id_from_worktree_path(homelab_repo_path: Path, wt_path: Path) -> str | None:
    """Derive run_id from a worktree path, or None if it doesn't match the pattern.

    Handles two naming conventions:
    1. Worktrees inside the homelab repo at ``worktrees/run-<id>``.
    2. Worktrees at an external worktrees_root at ``<worktrees_root>/run-<id>``.
    """
    try:
        relative = wt_path.resolve().relative_to(homelab_repo_path.resolve())
    except ValueError:
        # Not relative to homelab — could be under worktrees_root.
        # Try to match the tail segment "run-<id>" directly.
        wt_name = wt_path.name
        if wt_name.startswith("run-"):
            return wt_name[len("run-"):]
        return None

    parts = relative.parts
    # Pattern 1: <repo>/worktrees/run-<id>
    if len(parts) >= 2 and parts[0] == "worktrees" and parts[1].startswith("run-"):
        return parts[1][len("run-"):]
    return None


def _tmux_sessions_for_prefix(prefix: str = "symphony-") -> list[str]:
    """List tmux session names matching the prefix, filtering out non-existent."""

    result = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):  # 1 = no sessions
        return []
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith(prefix)
    ]


def _tmux_session_alive(session_name: str) -> bool:
    """Return True if a tmux session has at least one live client/window."""

    result = subprocess.run(
        ["tmux", "list-panes", "-t", session_name, "-F", "#{session_attached}"],
        capture_output=True,
        text=True,
        check=False,
    )
    # Non-zero exit or no output means no attached client.
    if result.returncode != 0:
        return False
    return result.stdout.strip() != "0"


def kill_tmux_session(run_id: str) -> None:
    """Kill the per-run tmux session if it exists and has no attached client."""

    session_name = tmux_session_name(run_id)
    existing = _tmux_sessions_for_prefix()
    if session_name not in existing:
        LOGGER.debug("tmux_session_already_gone run_id=%s session=%s", run_id, session_name)
        return
    if _tmux_session_alive(session_name):
        LOGGER.debug("tmux_session_owned_by_live_process run_id=%s session=%s", run_id, session_name)
        return

    result = subprocess.run(
        ["tmux", "kill-session", "-t", session_name],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        LOGGER.info("tmux_session_killed run_id=%s session=%s", run_id, session_name)
    else:
        LOGGER.warning(
            "tmux_session_kill_failed run_id=%s session=%s error=%s",
            run_id, session_name, result.stderr.strip(),
        )


def _git_checked(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Like subprocess.run with check=True, but captures output and returns it."""

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

    LOGGER.info("worktree_removed run_id=%s path=%s", run_id, wt_path)


def remove_worktree_if_exists(config: SymphonyConfig, run_id: str) -> None:
    """Remove the Run's worktree, suppressing WorktreeError on missing worktree.

    Use this on crash/timeout paths where the worktree may or may not have been
    created before the failure.
    """

    try:
        remove_worktree(config, run_id)
    except WorktreeError as exc:
        LOGGER.debug("worktree_cleanup_ignored run_id=%s error=%s", run_id, exc)