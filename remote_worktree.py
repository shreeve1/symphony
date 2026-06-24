"""Remote git worktree helpers for SSH-backed coding bindings."""

from __future__ import annotations

import logging
import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import ssh_support
from config import RemotePolicy
from web.api.worktree import branch_name, worktree_dir

LOGGER = logging.getLogger(__name__)

RunFunc = Callable[..., Any]


def create_worktree(
    remote: RemotePolicy,
    repo_path: Path,
    binding_name: str,
    issue_id: str,
    base_branch: str,
    *,
    run_func: RunFunc = subprocess.run,
) -> Path:
    wt_path = worktree_dir(repo_path, binding_name, issue_id)
    branch = branch_name(binding_name, issue_id)
    script = " && ".join(
        [
            f"if [ -d {shlex.quote(str(wt_path))} ]; then exit 0; fi",
            f"mkdir -p {shlex.quote(str(wt_path.parent))}",
            (
                f"if git -C {shlex.quote(str(repo_path))} show-ref --verify "
                f"refs/heads/{shlex.quote(branch)} >/dev/null 2>&1; then "
                f"git -C {shlex.quote(str(repo_path))} worktree add --checkout "
                f"{shlex.quote(str(wt_path))} {shlex.quote(branch)}; else "
                f"git -C {shlex.quote(str(repo_path))} worktree add --checkout -b "
                f"{shlex.quote(branch)} {shlex.quote(str(wt_path))} {shlex.quote(base_branch)}; fi"
            ),
        ]
    )
    _run(remote, script, run_func=run_func)
    LOGGER.info(
        "remote_worktree_created path=%s branch=%s base=%s",
        wt_path,
        branch,
        base_branch,
    )
    return wt_path


def worktree_exists(
    remote: RemotePolicy,
    repo_path: Path,
    binding_name: str,
    issue_id: str,
    *,
    run_func: RunFunc = subprocess.run,
) -> bool:
    wt_path = worktree_dir(repo_path, binding_name, issue_id)
    result = _run(
        remote,
        f"test -d {shlex.quote(str(wt_path))}",
        check=False,
        run_func=run_func,
    )
    return result.returncode == 0


def worktree_is_dirty(
    remote: RemotePolicy,
    repo_path: Path,
    binding_name: str,
    issue_id: str,
    *,
    run_func: RunFunc = subprocess.run,
) -> bool:
    wt_path = worktree_dir(repo_path, binding_name, issue_id)
    if not worktree_exists(
        remote, repo_path, binding_name, issue_id, run_func=run_func
    ):
        return False
    result = _run(
        remote,
        f"git -C {shlex.quote(str(wt_path))} status --porcelain",
        run_func=run_func,
    )
    return any(line.strip() for line in result.stdout.splitlines())


def base_repo_dirty(
    remote: RemotePolicy,
    repo_path: Path,
    *,
    run_func: RunFunc = subprocess.run,
) -> bool:
    result = _run(
        remote,
        f"git -C {shlex.quote(str(repo_path))} status --porcelain",
        run_func=run_func,
    )
    for line in result.stdout.splitlines():
        if line.startswith("?? worktrees/"):
            continue
        if line.strip():
            return True
    return False


def remove_worktree(
    remote: RemotePolicy,
    repo_path: Path,
    binding_name: str,
    issue_id: str,
    *,
    run_func: RunFunc = subprocess.run,
) -> None:
    wt_path = worktree_dir(repo_path, binding_name, issue_id)
    branch = branch_name(binding_name, issue_id)
    script = (
        f"if [ -d {shlex.quote(str(wt_path))} ]; then "
        f"git -C {shlex.quote(str(repo_path))} worktree remove --force {shlex.quote(str(wt_path))}; fi; "
        f"git -C {shlex.quote(str(repo_path))} branch -D {shlex.quote(branch)} >/dev/null 2>&1 || true"
    )
    _run(remote, script, run_func=run_func)
    LOGGER.info("remote_worktree_removed path=%s branch=%s", wt_path, branch)


def run_verification(
    remote: RemotePolicy,
    cwd: Path,
    command: str,
    *,
    run_func: RunFunc = subprocess.run,
) -> int:
    result = _run(
        remote,
        f"cd {shlex.quote(str(cwd))} && bash -lc {shlex.quote(command)}",
        check=False,
        timeout=None,
        run_func=run_func,
    )
    if result.returncode != 0:
        LOGGER.warning(
            "remote_review_verification_failed cwd=%s returncode=%s stdout=%r stderr=%r",
            cwd,
            result.returncode,
            result.stdout[-1000:],
            result.stderr[-1000:],
        )
    return int(result.returncode)


def land_worktree(
    remote: RemotePolicy,
    repo_path: Path,
    binding_name: str,
    issue_id: str,
    base_branch: str,
    *,
    run_func: RunFunc = subprocess.run,
) -> str | None:
    error = merge_worktree(
        remote, repo_path, binding_name, issue_id, base_branch, run_func=run_func
    )
    if error is not None:
        return error
    remove_worktree(remote, repo_path, binding_name, issue_id, run_func=run_func)
    return None


def merge_worktree(
    remote: RemotePolicy,
    repo_path: Path,
    binding_name: str,
    issue_id: str,
    base_branch: str,
    *,
    run_func: RunFunc = subprocess.run,
) -> str | None:
    wt_path = worktree_dir(repo_path, binding_name, issue_id)
    branch = branch_name(binding_name, issue_id)
    if (
        _run(
            remote,
            f"git -C {shlex.quote(str(repo_path))} checkout {shlex.quote(base_branch)}",
            check=False,
            run_func=run_func,
        ).returncode
        != 0
    ):
        return f"Auto-merge halted: checkout of base branch {base_branch} failed. Inspect remote worktree at {wt_path}."
    if (
        _run(
            remote,
            f"git -C {shlex.quote(str(repo_path))} merge --ff-only {shlex.quote(branch)}",
            check=False,
            run_func=run_func,
        ).returncode
        == 0
    ):
        LOGGER.info("remote_merge_succeeded branch=%s base=%s", branch, base_branch)
        return None
    _run(
        remote,
        f"git -C {shlex.quote(str(repo_path))} merge --abort",
        check=False,
        run_func=run_func,
    )
    if (
        _run(
            remote,
            f"git -C {shlex.quote(str(wt_path))} rebase {shlex.quote(base_branch)}",
            check=False,
            run_func=run_func,
        ).returncode
        != 0
    ):
        _run(
            remote,
            f"git -C {shlex.quote(str(wt_path))} rebase --abort",
            check=False,
            run_func=run_func,
        )
        return f"Auto-merge halted: FF-only merge of {branch} into {base_branch} failed. Inspect remote worktree at {wt_path}."
    if (
        _run(
            remote,
            f"git -C {shlex.quote(str(repo_path))} merge --ff-only {shlex.quote(branch)}",
            check=False,
            run_func=run_func,
        ).returncode
        == 0
    ):
        LOGGER.info(
            "remote_merge_rebase_retry_succeeded branch=%s base=%s", branch, base_branch
        )
        return None
    _run(
        remote,
        f"git -C {shlex.quote(str(repo_path))} merge --abort",
        check=False,
        run_func=run_func,
    )
    return f"Auto-merge halted: FF-only merge of {branch} into {base_branch} failed. Inspect remote worktree at {wt_path}."


def _run(
    remote: RemotePolicy,
    command: str,
    *,
    check: bool = True,
    timeout: float | None = 30,
    run_func: RunFunc = subprocess.run,
) -> subprocess.CompletedProcess:
    result = run_func(
        ssh_support.ssh_base_args(remote) + [command],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            ssh_support.ssh_base_args(remote) + [command],
            output=result.stdout,
            stderr=result.stderr,
        )
    return result
