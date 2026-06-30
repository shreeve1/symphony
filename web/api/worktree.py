"""Worktree management for Podium per-Issue persistent worktrees.

Worktree paths: ``<repo_path>/worktrees/<binding_name>/<issue_id>``
Branch names: ``podium/<binding_name>/<issue_id>``
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def worktree_dir(repo_path: Path, binding_name: str, issue_id: str) -> Path:
    """Return the worktree path for an issue."""
    return (repo_path / "worktrees" / binding_name / issue_id).resolve()


def branch_name(binding_name: str, issue_id: str) -> str:
    """Return the branch name for an issue's worktree."""
    return f"podium/{binding_name}/{issue_id}"


def worktree_exists(repo_path: Path, binding_name: str, issue_id: str) -> bool:
    """Check if the worktree already exists on disk."""
    return worktree_dir(repo_path, binding_name, issue_id).is_dir()


def create_worktree(
    repo_path: Path,
    binding_name: str,
    issue_id: str,
    base_branch: str,
) -> Path:
    """Create a git worktree at the standard path with the standard branch name.

    The branch is created from ``base_branch``. If the worktree already exists
    (idempotent), returns the existing path. If the branch already exists
    without a worktree (orphan ref), it is reused.

    Returns the worktree path.
    """
    wt_path = worktree_dir(repo_path, binding_name, issue_id)
    if wt_path.is_dir():
        LOGGER.info("worktree_already_exists path=%s", wt_path)
        return wt_path

    branch = branch_name(binding_name, issue_id)
    wt_path.parent.mkdir(parents=True, exist_ok=True)

    branch_exists = (
        _run_git(
            repo_path, ["show-ref", "--verify", f"refs/heads/{branch}"], check=False
        )
        is not None
    )
    if branch_exists:
        _run_git(repo_path, ["worktree", "add", "--checkout", str(wt_path), branch])
    else:
        _run_git(
            repo_path,
            [
                "worktree",
                "add",
                "--checkout",
                "-b",
                branch,
                str(wt_path),
                base_branch,
            ],
        )
    LOGGER.info(
        "worktree_created path=%s branch=%s base=%s",
        wt_path,
        branch,
        base_branch,
    )
    return wt_path


def remove_worktree(repo_path: Path, binding_name: str, issue_id: str) -> None:
    """Remove the worktree and its branch ref. Safe to call when already gone."""
    wt_path = worktree_dir(repo_path, binding_name, issue_id)
    branch = branch_name(binding_name, issue_id)

    if wt_path.is_dir():
        _run_git(repo_path, ["worktree", "remove", "--force", str(wt_path)])
        LOGGER.info("worktree_removed path=%s", wt_path)
    else:
        LOGGER.info("worktree_absent_skip path=%s", wt_path)

    # Remove the branch ref (if still present after worktree removal).
    _run_git(repo_path, ["branch", "-D", branch], check=False)
    LOGGER.info("worktree_branch_removed branch=%s", branch)


def base_repo_dirty(repo_path: Path) -> bool:
    """Return True if the base repo checkout has uncommitted changes.

    Git reports nested worktree directories as untracked from the base checkout;
    those are Podium-owned and should not block their own merge. All other
    porcelain entries, including other untracked files, count as dirty.
    """
    result = _run_git(repo_path, ["status", "--porcelain"], check=True)
    assert result is not None  # check=True guarantees str
    for line in result.splitlines():
        if len(line) > 3 and line[3:].startswith("worktrees/"):
            continue
        if line.strip():
            return True
    return False


def worktree_is_dirty(repo_path: Path, binding_name: str, issue_id: str) -> bool:
    """Return True if the Issue's worktree has uncommitted changes.

    Runs ``git status --porcelain`` *inside the worktree* (not the base repo).
    Any non-empty porcelain line — tracked modifications or untracked files —
    counts as dirty. Unlike :func:`base_repo_dirty`, untracked files are NOT
    excused: a leaf worktree has no nested Podium worktrees, so untracked files
    there are real agent output that must be committed before merge.

    Returns ``False`` when the worktree directory does not exist.
    """
    wt_path = worktree_dir(repo_path, binding_name, issue_id)
    if not wt_path.is_dir():
        return False
    result = _run_git(wt_path, ["status", "--porcelain"], check=True)
    assert result is not None  # check=True guarantees str
    return any(line.strip() for line in result.splitlines())


def worktree_diff_empty(
    repo_path: Path,
    binding_name: str,
    issue_id: str,
    base_branch: str = "main",
) -> bool:
    """Return True if the issue branch has no committed diff vs ``base_branch``.

    Missing worktree, branch, or base refs return False: unknown is not empty.
    """
    if not worktree_dir(repo_path, binding_name, issue_id).is_dir():
        return False

    branch = branch_name(binding_name, issue_id)
    if (
        _run_git(
            repo_path, ["show-ref", "--verify", f"refs/heads/{branch}"], check=False
        )
        is None
    ):
        return False
    if (
        _run_git(
            repo_path,
            ["rev-parse", "--verify", f"{base_branch}^{{commit}}"],
            check=False,
        )
        is None
    ):
        return False

    result = subprocess.run(
        ["git", "-C", str(repo_path), "diff", "--quiet", f"{base_branch}...{branch}"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    LOGGER.warning(
        "git_diff_quiet_failed base=%s branch=%s returncode=%s stderr=%s",
        base_branch,
        branch,
        result.returncode,
        result.stderr,
    )
    return False


def merge_worktree_preserving_base_wip(
    repo_path: Path,
    binding_name: str,
    issue_id: str,
    base_branch: str,
) -> str | None:
    """Merge while preserving dirty base-checkout WIP.

    Dirty base changes are stashed, the issue branch is merged, then the stash
    is restored. If the restore conflicts, the merged issue version wins for
    conflicted files; non-conflicting operator WIP stays in the working tree.
    """
    if not base_repo_dirty(repo_path):
        return merge_worktree(repo_path, binding_name, issue_id, base_branch)

    branch = branch_name(binding_name, issue_id)
    stash = _run_git(
        repo_path,
        [
            "stash",
            "push",
            "--include-untracked",
            "-m",
            f"symphony-base-wip-before-{branch}",
        ],
        check=False,
    )
    if stash is None:
        return (
            "Auto-merge halted: base checkout has uncommitted changes and "
            "Symphony could not stash them."
        )

    merge_error = merge_worktree(repo_path, binding_name, issue_id, base_branch)
    restore_error = _restore_stash_issue_wins(repo_path, "stash@{0}")
    if restore_error is not None:
        if merge_error is None:
            return restore_error
        return f"{merge_error} {restore_error}"
    return merge_error


def merge_worktree(
    repo_path: Path,
    binding_name: str,
    issue_id: str,
    base_branch: str,
) -> str | None:
    """Fast-forward-merge the worktree branch into ``base_branch``.

    Checks out ``base_branch`` in the base repo before merging and leaves the
    base checkout there after success. Returns ``None`` on success, or an
    error message string on failure. Does NOT remove the worktree — the caller
    decides what to do.
    """
    branch = branch_name(binding_name, issue_id)

    wt_path = worktree_dir(repo_path, binding_name, issue_id)
    checkout_ok = (
        _run_git(repo_path, ["checkout", base_branch], check=False) is not None
    )
    if not checkout_ok:
        return (
            f"Auto-merge halted: checkout of base branch {base_branch} failed. "
            f"Inspect worktree at {wt_path}."
        )

    try:
        subprocess.run(
            ["git", "-C", str(repo_path), "merge", "--ff-only", branch],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        LOGGER.info("merge_succeeded branch=%s base=%s", branch, base_branch)
        return None
    except subprocess.CalledProcessError as exc:
        LOGGER.warning(
            "merge_failed branch=%s base=%s stderr=%s",
            branch,
            base_branch,
            exc.stderr,
        )
        # Abort the failed merge to leave a clean checkout before retrying.
        subprocess.run(
            ["git", "-C", str(repo_path), "merge", "--abort"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        rebase = subprocess.run(
            ["git", "-C", str(wt_path), "rebase", base_branch],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if rebase.returncode != 0:
            LOGGER.warning(
                "merge_rebase_failed branch=%s base=%s stderr=%s",
                branch,
                base_branch,
                rebase.stderr,
            )
            subprocess.run(
                ["git", "-C", str(wt_path), "rebase", "--abort"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            return (
                f"Auto-merge halted: FF-only merge of {branch} into "
                f"{base_branch} failed. Inspect worktree at {wt_path}."
            )

        try:
            subprocess.run(
                ["git", "-C", str(repo_path), "merge", "--ff-only", branch],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            LOGGER.info(
                "merge_rebase_retry_succeeded branch=%s base=%s", branch, base_branch
            )
            return None
        except subprocess.CalledProcessError as retry_exc:
            LOGGER.warning(
                "merge_retry_failed branch=%s base=%s stderr=%s",
                branch,
                base_branch,
                retry_exc.stderr,
            )
            subprocess.run(
                ["git", "-C", str(repo_path), "merge", "--abort"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            return (
                f"Auto-merge halted: FF-only merge of {branch} into "
                f"{base_branch} failed. Inspect worktree at {wt_path}."
            )


def land_worktree(
    repo_path: Path,
    binding_name: str,
    issue_id: str,
    base_branch: str,
) -> str | None:
    """Merge an issue worktree and clean it up on success.

    Returns ``None`` on success, or the merge block reason on failure. This is
    intentionally process-neutral: no issue-state mutation and no redispatch.
    """
    error = merge_worktree_preserving_base_wip(
        repo_path, binding_name, issue_id, base_branch
    )
    if error is not None:
        return error
    cleanup_worktree(repo_path, binding_name, issue_id)
    return None


def cleanup_worktree(repo_path: Path, binding_name: str, issue_id: str) -> None:
    """Convenience: remove worktree + branch ref after a successful merge."""
    remove_worktree(repo_path, binding_name, issue_id)


def _restore_stash_issue_wins(repo_path: Path, stash_ref: str) -> str | None:
    apply = subprocess.run(
        ["git", "-C", str(repo_path), "stash", "apply", stash_ref],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if apply.returncode == 0:
        _run_git(repo_path, ["stash", "drop", stash_ref], check=False)
        return None

    unmerged = _run_git(
        repo_path, ["diff", "--name-only", "--diff-filter=U", "-z"], check=False
    )
    paths = [path for path in (unmerged or "").split("\0") if path]
    if not paths:
        return (
            "Auto-merge halted: issue branch landed, but restoring stashed base "
            "changes failed. Inspect `git stash list`."
        )

    for path in paths:
        checkout = subprocess.run(
            ["git", "-C", str(repo_path), "checkout", "--ours", "--", path],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if checkout.returncode != 0:
            return (
                "Auto-merge halted: issue branch landed, but resolving stashed "
                f"base changes for {path} failed. Inspect `git stash list`."
            )
        _run_git(repo_path, ["add", "--", path], check=False)

    remaining = _run_git(
        repo_path, ["diff", "--name-only", "--diff-filter=U"], check=False
    )
    if remaining and remaining.strip():
        return (
            "Auto-merge halted: issue branch landed, but some stashed base "
            "changes still conflict. Inspect `git status` and `git stash list`."
        )

    _run_git(repo_path, ["stash", "drop", stash_ref], check=False)
    LOGGER.info("base_wip_restored_issue_wins conflicts=%s", paths)
    return None


def _run_git(repo_path: Path, args: list[str], *, check: bool = True) -> str | None:
    """Run a git command in ``repo_path``.

    Returns stdout on success. If ``check`` is False, returns ``None`` on
    non-zero exit instead of raising.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            LOGGER.warning(
                "git_command_failed args=%s returncode=%s stderr=%s",
                args,
                result.returncode,
                result.stderr,
            )
            if not check:
                return None
            raise subprocess.CalledProcessError(
                result.returncode,
                ["git", "-C", str(repo_path), *args],
                output=result.stdout,
                stderr=result.stderr,
            )
        return result.stdout
    except subprocess.CalledProcessError as exc:
        LOGGER.warning(
            "git_command_failed args=%s returncode=%s stderr=%s",
            args,
            exc.returncode,
            exc.stderr,
        )
        if not check:
            return None
        raise
    except subprocess.TimeoutExpired as exc:
        LOGGER.error("git_command_timeout args=%s", args)
        if not check:
            return None
        raise RuntimeError(f"git command timed out: {args}") from exc
