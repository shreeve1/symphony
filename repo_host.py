"""RepoHost seam for resolving a binding's git code sha (ADR-0012).

A binding's ``repo_path`` may be local (run ``git`` directly) or remote (run
``git`` over SSH on another host). ``RepoHost`` is the minimal abstraction the
dispatch pipeline routes its ``code_sha()`` reads through, so a remote binding
no longer assumes ``repo_path`` is a local directory.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Callable, Protocol

import ssh_support
from code_version import UNKNOWN, resolve_code_sha
from config import RemotePolicy


class RepoHost(Protocol):
    """A repository whose git code sha can be resolved."""

    def code_sha(self) -> str:
        """Return the short git sha, or ``"unknown"`` on failure."""
        ...


class LocalRepoHost:
    """Resolve the code sha of a local checkout via ``git`` in ``path``.

    ``path`` is the dispatch cwd, not necessarily ``binding.repo_path``: for a
    local worktree-active issue it is the per-issue worktree, so the recorded
    sha stays the worktree HEAD.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def code_sha(self) -> str:
        return resolve_code_sha(self.path)


class SshRepoHost:
    """Resolve the code sha of a remote checkout via ``git`` over SSH.

    Worktrees are disabled for remote bindings, so ``repo_path`` is used
    directly. Never raises: maps non-zero exit / ``OSError`` /
    ``subprocess.TimeoutExpired`` to ``"unknown"`` with a bounded 5s timeout
    matching ``resolve_code_sha``.
    """

    def __init__(
        self,
        remote: RemotePolicy,
        repo_path: Path,
        run_func: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ) -> None:
        self.remote = remote
        self.repo_path = repo_path
        self.run_func = run_func

    def code_sha(self) -> str:
        remote_command = (
            f"git -C {shlex.quote(str(self.repo_path))} rev-parse --short HEAD"
        )
        argv = ssh_support.ssh_base_args(self.remote) + [remote_command]
        try:
            result = self.run_func(
                argv,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return UNKNOWN
        if result.returncode != 0:
            return UNKNOWN
        sha = result.stdout.strip()
        return sha or UNKNOWN


def repo_host_for(
    binding,
    *,
    cwd: Path | None = None,
    run_func: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> RepoHost:
    """Return the right ``RepoHost`` for ``binding``.

    Remote bindings get an ``SshRepoHost`` bound to ``binding.repo_path`` (cwd
    ignored — worktrees are off remotely). Local bindings get a
    ``LocalRepoHost`` bound to ``cwd or binding.repo_path``, preserving local
    worktree-HEAD sha semantics.
    """

    if binding.is_remote:
        return SshRepoHost(binding.remote, binding.repo_path, run_func)
    return LocalRepoHost(cwd or binding.repo_path)
