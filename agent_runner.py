"""Launch pi agents for Symphony issues."""

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
from typing import Callable, Protocol

from config import SymphonyConfig
from plane_poller import CandidateIssue


LOGGER = logging.getLogger(__name__)
TERMINATE_GRACE_SECONDS = 5
PI_HELP_TIMEOUT_SECONDS = 30
PI_PROBE_TIMEOUT_SECONDS = 30


class AgentRunnerError(RuntimeError):
    """Raised when pi cannot be launched safely."""


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


def verify_pi_support(
    pi_bin: str,
    provider: str,
    model: str,
    cwd: Path | str,
    run_func: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    """Fail fast if the configured pi binary cannot run print/no-session mode."""

    try:
        result = run_func(
            [pi_bin, "--help"],
            capture_output=True,
            text=True,
            check=False,
            timeout=PI_HELP_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise AgentRunnerError(
            f"Configured pi help check timed out after {PI_HELP_TIMEOUT_SECONDS}s"
        ) from exc
    except OSError as exc:
        raise AgentRunnerError(f"Configured pi binary could not be executed: {exc}") from exc
    output = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0 or "--print" not in output or "--no-session" not in output:
        raise AgentRunnerError(
            "Configured pi binary does not advertise `--print --no-session` support"
        )
    command = [
        pi_bin,
        "--print",
        "--no-session",
        "--provider",
        provider,
        "--model",
        model,
        "ping",
    ]
    try:
        probe = run_func(
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd),
            timeout=PI_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise AgentRunnerError(
            f"Configured pi probe timed out after {PI_PROBE_TIMEOUT_SECONDS}s; provider/model/auth may be invalid"
        ) from exc
    except OSError as exc:
        raise AgentRunnerError(f"Configured pi probe could not be executed: {exc}") from exc
    if probe.returncode != 0:
        raise AgentRunnerError(
            f"Configured pi probe failed with exit code {probe.returncode}: {probe.stderr.strip()}"
        )
    if not probe.stdout.strip():
        raise AgentRunnerError(
            "Configured pi probe produced empty stdout; provider/model/auth may be invalid"
        )


def run_agent(
    config: SymphonyConfig,
    issue: CandidateIssue,
    rendered_prompt: str,
    *,
    plane_cli_source: Path | None = None,
    popen_factory: Callable[..., ProcessLike] = subprocess.Popen,
    mkdtemp: Callable[..., str] = tempfile.mkdtemp,
    copy_file: Callable[[Path, Path], object] = shutil.copy2,
    remove_tree: Callable[[str], object] = shutil.rmtree,
    kill_process_group: Callable[[int, int], object] = os.killpg,
    clock: Callable[[], float] = time.monotonic,
    environ: dict[str, str] | None = None,
) -> AgentResult:
    """Run pi for a Plane issue with a temporary Plane helper in PATH."""

    helper_source = plane_cli_source or Path(__file__).with_name("plane_cli.py")
    temp_dir = mkdtemp(prefix="symphony-plane-cli-")
    started = clock()
    process: ProcessLike | None = None
    try:
        Path(temp_dir).mkdir(parents=True, exist_ok=True)
        helper_target = Path(temp_dir) / "plane"
        copy_file(helper_source, helper_target)
        helper_target.chmod(0o700)

        source_env = os.environ if environ is None else environ
        # TERM is deliberately NOT inherited. We override with TERM=dumb and
        # NO_COLOR=1 below so the pi CLI (and any tool it spawns) cannot emit
        # ANSI escapes or progress trace into our captured stderr. Plane
        # renders fenced blocks as plain text; ANSI is pure noise there.
        allowed_keys = {
            "PATH", "HOME", "USER", "LANG", "XDG_RUNTIME_DIR",
            "PYTHONUNBUFFERED", "TMPDIR",
            "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_HOME_CHANNEL",
            "ZAI_API_KEY", "PI_OFFLINE", "PI_CODING_AGENT_DIR",
            "PI_CODING_AGENT_SESSION_DIR",
        }
        env = {k: v for k, v in source_env.items() if k in allowed_keys}
        env.update(
            {
                "PATH": f"{temp_dir}{os.pathsep}{source_env.get('PATH', '')}",
                "HOME": source_env.get("HOME", f"/home/{os.getenv('USER', 'james')}"),
                "TERM": "dumb",
                "NO_COLOR": "1",
                "SYMPHONY_ISSUE_ID": issue.id,
                "SYMPHONY_PLANE_API_URL": config.plane_api_url,
                "SYMPHONY_PLANE_FRONTEND_URL": config.plane_frontend_url,
                "PLANE_DASHBOARD_URL": config.plane_dashboard_url,
                "SYMPHONY_PLANE_API_KEY": config.plane_api_key,
                "SYMPHONY_PLANE_PROJECT_ID": config.plane_project_id,
                "SYMPHONY_PLANE_WORKSPACE_SLUG": config.plane_workspace_slug,
                "PYTHONPATH": str(Path(__file__).parent),
            }
        )

        command = [
            config.pi_bin,
            "--print",
            "--no-session",
            "--provider",
            config.pi_provider,
            "--model",
            config.pi_model,
            rendered_prompt,
        ]
        LOGGER.info(
            "pi_dispatch issue_id=%s provider=%s model=%s",
            issue.id, config.pi_provider, config.pi_model,
        )
        process = popen_factory(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=str(config.homelab_repo_path),
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
            if exit_code == 0 and not stdout.strip() and not stderr.strip():
                message = (
                    "pi exited 0 with empty stdout/stderr; treating as failure because "
                    "provider/model/auth misconfiguration can otherwise look successful"
                )
                LOGGER.warning("pi_silent_exit issue_id=%s", issue.id)
                return AgentResult(137, duration_ms, False, stdout, message)
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
