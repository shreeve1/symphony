"""Tests for the RepoHost seam (ADR-0012, repo_host.py)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from config import DEFAULT_CONTRACT, ProjectBinding, RemotePolicy
from repo_host import LocalRepoHost, SshRepoHost, repo_host_for


class Completed:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(path), "init", "-b", "main"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@test"], check=True
    )
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    (path / "README.md").write_text("# test\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "initial"], check=True)


def _local_binding(repo: Path) -> ProjectBinding:
    return ProjectBinding(
        name="homelab",
        plane_project_id="homelab",
        repo_path=repo,
        base_branch="main",
        tracker_contract=DEFAULT_CONTRACT,
    )


def _remote_binding(repo: str = "/home/itadmin/symphony") -> ProjectBinding:
    return ProjectBinding(
        name="n8n",
        plane_project_id="n8n",
        repo_path=Path(repo),
        base_branch="main",
        tracker_contract=DEFAULT_CONTRACT,
        tracker="podium",
        remote=RemotePolicy(host="100.95.224.218", user="itadmin"),
    )


# T.2.1
def test_local_repo_host_returns_short_sha(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    expected = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    sha = LocalRepoHost(tmp_path).code_sha()

    assert sha == expected
    assert sha != "unknown"


# T.2.2
def test_local_repo_host_unknown_for_non_git(tmp_path: Path) -> None:
    assert LocalRepoHost(tmp_path).code_sha() == "unknown"


# T.3.1
def test_ssh_repo_host_builds_argv_and_returns_trimmed_stdout() -> None:
    calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed(returncode=0, stdout="abc1234\n")

    host = SshRepoHost(
        RemotePolicy(host="h", user="u"),
        Path("/home/itadmin/itastack"),
        run_func=fake_run,
    )

    sha = host.code_sha()

    assert sha == "abc1234"
    argv = calls[0][0]
    assert argv[:3] == ["ssh", "-o", "BatchMode=yes"]
    assert argv[-2] == "u@h"
    assert argv[-1] == "git -C /home/itadmin/itastack rev-parse --short HEAD"
    assert calls[0][1]["timeout"] == 5


# T.3.2
def test_ssh_repo_host_maps_failures_to_unknown() -> None:
    def nonzero(command, **kwargs):
        return Completed(returncode=128, stderr="not a git repo")

    def raises_oserror(command, **kwargs):
        raise OSError("ssh broken")

    def raises_timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(cmd=command, timeout=5)

    remote = RemotePolicy(host="h", user="u")
    repo = Path("/remote/repo")

    assert SshRepoHost(remote, repo, run_func=nonzero).code_sha() == "unknown"
    assert SshRepoHost(remote, repo, run_func=raises_oserror).code_sha() == "unknown"
    assert SshRepoHost(remote, repo, run_func=raises_timeout).code_sha() == "unknown"


# T.3.2 (path quoting)
def test_ssh_repo_host_quotes_remote_path_with_spaces() -> None:
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return Completed(returncode=0, stdout="deadbee\n")

    SshRepoHost(
        RemotePolicy(host="h", user="u"),
        Path("/home/itadmin/ita stack"),
        run_func=fake_run,
    ).code_sha()

    assert calls[0][-1] == ("git -C '/home/itadmin/ita stack' rev-parse --short HEAD")


# T.3.3
def test_repo_host_for_routes_by_remoteness(tmp_path: Path) -> None:
    assert isinstance(repo_host_for(_remote_binding()), SshRepoHost)
    assert isinstance(repo_host_for(_local_binding(tmp_path)), LocalRepoHost)


# T.3.4
def test_repo_host_for_binds_local_and_remote_to_cwd(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    base = tmp_path / "base"
    local = repo_host_for(_local_binding(base), cwd=worktree)
    assert isinstance(local, LocalRepoHost)
    assert local.path == worktree

    remote_binding = _remote_binding("/home/itadmin/itastack")
    remote = repo_host_for(remote_binding, cwd=worktree)
    assert isinstance(remote, SshRepoHost)
    assert remote.repo_path == worktree
