"""Launch OpenCode agents for Symphony issues."""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, Sequence

from config import SymphonyConfig
from plane_poller import CandidateIssue


LOGGER = logging.getLogger(__name__)
TERMINATE_GRACE_SECONDS = 5


class AgentRunnerError(RuntimeError):
    """Raised when OpenCode cannot be launched safely."""


class ProcessLike(Protocol):
    pid: int
    returncode: int | None

    def communicate(self, timeout: float | None = None) -> tuple[str, str]: ...


@dataclass(frozen=True)
class AgentResult:
    exit_code: int
    duration_ms: int
    timed_out: bool
    stdout: str = ""
    stderr: str = ""


def verify_opencode_support(
    opencode_bin: str,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    """Fail fast if the configured OpenCode binary lacks run/agent support."""

    result = run_func(
        [opencode_bin, "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0 or "run" not in output or "--agent" not in output:
        raise AgentRunnerError(
            "Configured OpenCode binary does not advertise `run --agent` support"
        )


def run_agent(
    config: SymphonyConfig,
    issue: CandidateIssue,
    rendered_prompt: str,
    *,
    plane_cli_source: Path | None = None,
    popen_factory: Callable[..., ProcessLike] = subprocess.Popen,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    mkdtemp: Callable[..., str] = tempfile.mkdtemp,
    copy_file: Callable[[Path, Path], object] = shutil.copy2,
    remove_tree: Callable[[str], object] = shutil.rmtree,
    kill_process_group: Callable[[int, int], object] = os.killpg,
    clock: Callable[[], float] = time.monotonic,
    environ: dict[str, str] | None = None,
) -> AgentResult:
    """Run OpenCode for a Plane issue with a temporary Plane helper in PATH."""

    verify_opencode_support(config.opencode_bin, run_func=run_func)

    helper_source = plane_cli_source or Path(__file__).with_name("plane_cli.py")
    temp_dir = mkdtemp(prefix="symphony-plane-cli-")
    started = clock()
    process: ProcessLike | None = None
    try:
        Path(temp_dir).mkdir(parents=True, exist_ok=True)
        helper_target = Path(temp_dir) / "plane"
        copy_file(helper_source, helper_target)
        helper_target.chmod(0o700)

        env = dict(os.environ if environ is None else environ)
        env.update(
            {
                "PATH": f"{temp_dir}{os.pathsep}{env.get('PATH', '')}",
                "SYMPHONY_ISSUE_ID": issue.id,
                "SYMPHONY_PLANE_API_URL": config.plane_api_url,
                "SYMPHONY_PLANE_API_KEY": config.plane_api_key,
                "SYMPHONY_PLANE_PROJECT_ID": config.plane_project_id,
                "SYMPHONY_PLANE_WORKSPACE_SLUG": config.plane_workspace_slug,
            }
        )

        command = [
            config.opencode_bin,
            "run",
            "--agent",
            "executor-ssh",
            "--dir",
            str(config.homelab_repo_path),
            "--title",
            f"symphony-{issue.id}",
            rendered_prompt,
        ]
        LOGGER.info("agent_started issue_id=%s title=symphony-%s", issue.id, issue.id)
        process = popen_factory(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=config.run_timeout_ms / 1000)
            duration_ms = int((clock() - started) * 1000)
            exit_code = int(process.returncode or 0)
            LOGGER.info(
                "agent_exited issue_id=%s exit_code=%s duration_ms=%s timed_out=false",
                issue.id,
                exit_code,
                duration_ms,
            )
            return AgentResult(exit_code, duration_ms, False, stdout, stderr)
        except subprocess.TimeoutExpired:
            stdout, stderr = _terminate_process_group(
                process,
                kill_process_group=kill_process_group,
            )
            duration_ms = int((clock() - started) * 1000)
            LOGGER.info(
                "agent_exited issue_id=%s exit_code=-1 duration_ms=%s timed_out=true",
                issue.id,
                duration_ms,
            )
            return AgentResult(-1, duration_ms, True, stdout, stderr)
    finally:
        remove_tree(temp_dir)


def _terminate_process_group(
    process: ProcessLike,
    *,
    kill_process_group: Callable[[int, int], object],
) -> tuple[str, str]:
    kill_process_group(process.pid, signal.SIGTERM)
    try:
        return process.communicate(timeout=TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        kill_process_group(process.pid, signal.SIGKILL)
        return process.communicate()
