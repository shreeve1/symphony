"""Launch pi agents for Symphony issues."""

from __future__ import annotations

import io
import json
import logging
import os
import re
import selectors
import shlex
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from importlib import import_module
from io import TextIOBase
from pathlib import Path
from typing import Protocol, cast

import ssh_support
from config import ProjectBinding, SymphonyConfig
from model_catalog import KNOWN_AGENTS
from plane_poller import CandidateIssue
from proc_runtime import (
    DEFAULT_RUNTIME_DIR,
    RPC_RUNTIME_DIR_ENV,
    pid_alive,
    pid_start_time,
    tail_spool_path,
)
from session_continuity import derive_session_id


LOGGER = logging.getLogger(__name__)
TERMINATE_GRACE_SECONDS = 5
PI_HELP_TIMEOUT_SECONDS = 30
PI_PROBE_TIMEOUT_SECONDS = 30
PI_RPC_PROBE_TIMEOUT_SECONDS = 20
RPC_STEER_POLL_INTERVAL_SECONDS = 0.5
# Cap the live-tail spool so a verbose/long remote run can't grow unbounded on
# the tmpfs runtime dir (/run). Matches the run-log ceiling; the full output is
# still captured in the (also-capped) run log at exit. ponytail: hard stop at
# the cap rather than a ring buffer — the in-place truncate a ring buffer needs
# would desync the byte-offset tailer; upgrade to rotation only if the frozen
# tail past 1 MiB of prose ever matters.
TAIL_SPOOL_MAX_BYTES = 1_048_576
# Pidfile registry for live `pi --mode rpc` processes. Each dispatch writes
# <runtime_dir>/rpc/<pid>.pid on launch and removes it on exit; for remote RPC
# runs this is the local SSH client pid, not the remote pi pid. A boot sweep
# (reap_orphan_rpc_processes) kills any local pi/SSH handles a crashed scheduler
# left behind, the RPC analogue of reap_orphan_claude_sockets (#058 orphan reaping).


def _rpc_pidfile_dir(environ: Mapping[str, str] | None = None) -> Path:
    source = os.environ if environ is None else environ
    runtime_dir = Path(source.get(RPC_RUNTIME_DIR_ENV, str(DEFAULT_RUNTIME_DIR)))
    return runtime_dir / "rpc"


class AgentRunnerError(RuntimeError):
    """Raised when pi cannot be launched safely."""


class CompletedLike(Protocol):
    @property
    def stdout(self) -> str: ...

    @property
    def stderr(self) -> str: ...

    @property
    def returncode(self) -> int: ...


class ProcessLike(Protocol):
    @property
    def pid(self) -> int: ...

    @property
    def returncode(self) -> int | None: ...

    def communicate(self, timeout: float | None = None) -> tuple[str, str]: ...


class RpcProcessLike(ProcessLike, Protocol):
    @property
    def stdin(self) -> TextIOBase: ...

    @property
    def stdout(self) -> TextIOBase: ...

    @property
    def stderr(self) -> TextIOBase: ...

    def poll(self) -> int | None: ...

    def wait(self, timeout: float | None = None) -> int: ...


class SteerReader(Protocol):
    def __call__(
        self, run_id: str, offset: int, *, environ: Mapping[str, str]
    ) -> tuple[list[Mapping[str, object]], int]: ...


@dataclass(frozen=True)
class AgentResult:
    exit_code: int
    duration_ms: int
    timed_out: bool
    stdout: str = ""
    stderr: str = ""


def _build_pi_command(
    pi_bin: str,
    provider: str,
    model: str,
    *,
    skill_source: str = "",
    rendered_prompt: str | None = None,
    session_id: str | None = None,
) -> list[str]:
    command = [pi_bin]
    if session_id is None:
        command += ["--print", "--no-session"]
    else:
        command += ["--mode", "rpc"]
    command += ["--provider", provider, "--model", model]
    if session_id is not None:
        command += ["--session-id", session_id]
    if skill_source:
        command += ["--skill", str(Path(skill_source).parent)]
    if rendered_prompt is not None:
        command.append(rendered_prompt)
    return command


def _silent_exit_result(
    *,
    issue_id: str,
    exit_code: int,
    duration_ms: int,
    stdout: str,
    stderr: str,
    message: str,
    log_event: str,
) -> AgentResult | None:
    if exit_code == 0 and not stdout.strip() and not stderr.strip():
        LOGGER.warning("%s issue_id=%s", log_event, issue_id)
        return AgentResult(137, duration_ms, False, stdout, message)
    return None


class AgentAdapter(Protocol):
    """Common dispatch contract for agent implementations."""

    def __call__(
        self, issue: CandidateIssue, rendered_prompt: str, /
    ) -> AgentResult: ...


def verify_pi_support(
    pi_bin: str,
    provider: str,
    model: str,
    cwd: Path | str,
    run_func: Callable[..., CompletedLike] = subprocess.run,
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
        raise AgentRunnerError(
            f"Configured pi binary could not be executed: {exc}"
        ) from exc
    output = f"{result.stdout}\n{result.stderr}"
    if (
        result.returncode != 0
        or "--print" not in output
        or "--no-session" not in output
    ):
        raise AgentRunnerError(
            "Configured pi binary does not advertise `--print --no-session` support"
        )
    command = _build_pi_command(
        pi_bin,
        provider,
        model,
        rendered_prompt="ping",
    )
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
        raise AgentRunnerError(
            f"Configured pi probe could not be executed: {exc}"
        ) from exc
    if probe.returncode != 0:
        raise AgentRunnerError(
            f"Configured pi probe failed with exit code {probe.returncode}: {probe.stderr.strip()}"
        )
    if not probe.stdout.strip():
        raise AgentRunnerError(
            "Configured pi probe produced empty stdout; provider/model/auth may be invalid"
        )


def _uses_plane_tracker(
    config: SymphonyConfig, binding: ProjectBinding | None = None
) -> bool:
    if binding is not None:
        return binding.tracker == "plane"
    if config.bindings:
        return config.bindings[0].tracker == "plane"
    return True


def _tracker_callback_env(config: SymphonyConfig) -> dict[str, str]:
    """Callback env exposed only to Plane-tracker agents for compatibility."""

    return {
        "SYMPHONY_TRACKER_API_URL": config.tracker_api_url,
        "SYMPHONY_TRACKER_FRONTEND_URL": config.tracker_frontend_url,
        "SYMPHONY_TRACKER_DASHBOARD_URL": config.tracker_dashboard_url,
        "SYMPHONY_TRACKER_API_KEY": config.tracker_api_key,
        "SYMPHONY_TRACKER_PROJECT_ID": config.tracker_project_id,
        "SYMPHONY_TRACKER_WORKSPACE_SLUG": config.tracker_workspace_slug,
        "SYMPHONY_PLANE_API_URL": config.plane_api_url,
        "SYMPHONY_PLANE_FRONTEND_URL": config.plane_frontend_url,
        "PLANE_DASHBOARD_URL": config.plane_dashboard_url,
        "SYMPHONY_PLANE_API_KEY": config.plane_api_key,
        "SYMPHONY_PLANE_PROJECT_ID": config.plane_project_id,
        "SYMPHONY_PLANE_WORKSPACE_SLUG": config.plane_workspace_slug,
    }


def _agent_env(
    config: SymphonyConfig,
    issue: CandidateIssue,
    temp_dir: str,
    source_env: Mapping[str, str],
) -> dict[str, str]:
    # TERM is deliberately NOT inherited. We override with TERM=dumb and
    # NO_COLOR=1 below so the pi CLI (and any tool it spawns) cannot emit
    # ANSI escapes or progress trace into our captured stderr. Plane
    # renders fenced blocks as plain text; ANSI is pure noise there.
    allowed_keys = {
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "XDG_RUNTIME_DIR",
        "PYTHONUNBUFFERED",
        "TMPDIR",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_HOME_CHANNEL",
        "ZAI_API_KEY",
        "PI_OFFLINE",
        "PI_CODING_AGENT_DIR",
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
            "PYTHONPATH": str(Path(__file__).parent),
        }
    )
    if _uses_plane_tracker(config):
        env.update(_tracker_callback_env(config))
    return env


def run_agent(
    config: SymphonyConfig,
    issue: CandidateIssue,
    rendered_prompt: str,
    *,
    plane_cli_source: Path | None = None,
    popen_factory: Callable[..., ProcessLike] | None = None,
    mkdtemp: Callable[..., str] = tempfile.mkdtemp,
    copy_file: Callable[[Path, Path], object] = shutil.copy2,
    remove_tree: Callable[[str], object] = shutil.rmtree,
    kill_process_group: Callable[[int, int], object] = os.killpg,
    clock: Callable[[], float] = time.monotonic,
    environ: dict[str, str] | None = None,
) -> AgentResult:
    """Run pi for an issue, shipping the Plane helper only for Plane bindings."""

    helper_source = plane_cli_source or Path(__file__).with_name("plane_cli.py")
    if popen_factory is None:
        popen_factory = cast(Callable[..., ProcessLike], subprocess.Popen)
    temp_dir = mkdtemp(prefix="symphony-plane-cli-")
    started = clock()
    process: ProcessLike | None = None

    # Worktree setup: create per-Issue worktree when worktree_active is True.
    # The worktree persists after the run — cleanup happens on merge-on-done.
    worktree_path: Path | None = None
    if getattr(issue, "worktree_active", False):
        create_worktree = import_module("worktree_facade").create_worktree

        binding_name = getattr(issue, "binding_name", "") or (
            config.bindings[0].name if config.bindings else ""
        )
        base_branch = getattr(issue, "base_branch", "") or config.base_branch
        try:
            worktree_path = create_worktree(
                config.homelab_repo_path,
                binding_name,
                issue.id,
                base_branch or "main",
            )
            LOGGER.info(
                "worktree_prepared issue_id=%s binding=%s path=%s",
                issue.id,
                binding_name,
                worktree_path,
            )
        except Exception as exc:
            LOGGER.error(
                "worktree_create_failed issue_id=%s error=%s",
                issue.id,
                exc,
            )
            raise AgentRunnerError(f"Worktree creation failed: {exc}") from exc

    try:
        Path(temp_dir).mkdir(parents=True, exist_ok=True)
        if _uses_plane_tracker(config):
            helper_target = Path(temp_dir) / "plane"
            copy_file(helper_source, helper_target)
            helper_target.chmod(0o700)

        source_env = os.environ if environ is None else environ
        env = _agent_env(config, issue, temp_dir, source_env)

        # Provider/model are resolved per-issue from models.yml by the
        # scheduler's dispatch gate; the config values are the legacy
        # Plane-path fallback only.
        provider = getattr(issue, "resolved_provider", "") or config.pi_provider
        model = getattr(issue, "resolved_model", "") or config.pi_model
        skill_source = getattr(issue, "skill_source", "")
        # pi does not discover ~/.claude/skills on its own; load the issue's
        # preferred skill explicitly (directory form keeps any skill assets
        # alongside SKILL.md available).
        command = _build_pi_command(
            config.pi_bin,
            provider,
            model,
            skill_source=skill_source,
            rendered_prompt=rendered_prompt,
        )
        cwd = str(worktree_path or config.homelab_repo_path)
        LOGGER.info(
            "pi_dispatch issue_id=%s provider=%s model=%s cwd=%s",
            issue.id,
            provider,
            model,
            cwd,
        )
        process = popen_factory(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=cwd,
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
            silent_result = _silent_exit_result(
                issue_id=issue.id,
                exit_code=exit_code,
                duration_ms=duration_ms,
                stdout=stdout,
                stderr=stderr,
                message=(
                    "pi exited 0 with empty stdout/stderr; treating as failure because "
                    "provider/model/auth misconfiguration can otherwise look successful"
                ),
                log_event="pi_silent_exit",
            )
            if silent_result is not None:
                return silent_result
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


def _remote_callback_port(api_url: str) -> int:
    """Port the remote agent reaches over the SSH reverse tunnel (ADR-0012).

    The tracker API is loopback-only on aidev; the remote writes to its own
    ``127.0.0.1:<port>`` which ``ssh -R`` tunnels back. Defaults to 8000 when
    the URL carries no explicit port.
    """

    match = re.search(r":(\d+)(?:/|$)", api_url)
    return int(match.group(1)) if match else 8000


def _remote_exports(
    config: SymphonyConfig, issue: CandidateIssue, *, binding: ProjectBinding
) -> dict[str, str]:
    """Tracker-callback env forwarded to the remote agent.

    Mirrors the SYMPHONY_* keys from ``_agent_env`` but omits local-only values
    (PATH/HOME/PYTHONPATH/TMPDIR) — the remote host supplies its own. Plane
    callback keys are included only for Plane bindings.
    """

    exports = {
        "SYMPHONY_ISSUE_ID": issue.id,
        "TERM": "dumb",
        "NO_COLOR": "1",
    }
    if _uses_plane_tracker(config, binding):
        exports.update(_tracker_callback_env(config))
    return exports


def _build_remote_command(
    *,
    repo_path: str,
    exports: Mapping[str, str],
    pi_command: list[str],
    helper_dir: str,
) -> str:
    """A single shell command line to run on the remote host over SSH.

    ``cd <repo> && export K=V... && PATH=<helper_dir>:$PATH <pi ...>`` — every
    value shell-quoted so prompts, paths, and secrets survive the remote shell.
    For Plane bindings, the helper dir carrying the shipped ``plane`` callback
    CLI is prepended to PATH so the agent can report back through the reverse
    tunnel. For Podium bindings, no helper dir is prepended.
    """

    export_str = " ".join(
        f"export {key}={shlex.quote(value)};" for key, value in exports.items()
    )
    pi_str = " ".join(shlex.quote(part) for part in pi_command)
    path_prefix = f"PATH={shlex.quote(helper_dir)}:$PATH " if helper_dir else ""
    return f"cd {shlex.quote(repo_path)} && {export_str} {path_prefix}{pi_str}"


def _ssh_base_args(remote, *, reverse_port: int | None = None) -> list[str]:
    return ssh_support.ssh_base_args(remote, reverse_port=reverse_port)


def _cleanup_remote_tmp(
    remote,
    remote_tmp: str,
    *,
    run_func: Callable[..., CompletedLike],
) -> None:
    if not remote_tmp:
        return
    with suppress(Exception):
        run_func(
            _ssh_base_args(remote) + [f"rm -rf {shlex.quote(remote_tmp)}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=PI_HELP_TIMEOUT_SECONDS,
        )


def _tar_directory_bytes(source_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for child in sorted(source_dir.iterdir()):
            archive.add(child, arcname=child.name)
    return buffer.getvalue()


def _stderr_text(result: CompletedLike) -> str:
    stderr = result.stderr
    if isinstance(stderr, bytes):
        return stderr.decode("utf-8", "replace")
    return str(stderr)


def run_remote_agent(
    config: SymphonyConfig,
    issue: CandidateIssue,
    rendered_prompt: str,
    *,
    binding: ProjectBinding,
    plane_cli_source: Path | None = None,
    run_func: Callable[..., CompletedLike] = subprocess.run,
    popen_factory: Callable[..., RpcProcessLike] | None = None,
    kill_process_group: Callable[[int, int], object] = os.killpg,
    clock: Callable[[], float] = time.monotonic,
    environ: dict[str, str] | None = None,
) -> AgentResult:
    """Run pi RPC on a remote host over SSH (ADR-0012).

    Ships the ``plane`` callback helper only for Plane bindings and ships the
    selected skill directory when an issue has ``preferred_skill``. Then runs
    ``ssh -R <port>:127.0.0.1:<port> user@host 'cd <repo> && ... pi --mode rpc'``.
    The SSH process stdin/stdout are the pi RPC pipe, so steering and session
    resume follow the local coding-binding path.
    """

    remote = binding.remote
    if remote is None:
        raise AgentRunnerError("run_remote_agent called for a non-remote binding")
    if popen_factory is None:
        popen_factory = cast(Callable[..., RpcProcessLike], subprocess.Popen)

    helper_source = plane_cli_source or Path(__file__).with_name("plane_cli.py")
    ship_plane_helper = _uses_plane_tracker(config, binding)
    helper_text = helper_source.read_text() if ship_plane_helper else ""
    skill_source = getattr(issue, "skill_source", "")
    needs_remote_tmp = ship_plane_helper or bool(skill_source)
    remote_tmp = f"/tmp/symphony-remote-{issue.id}" if needs_remote_tmp else ""
    started = clock()
    source_env = os.environ if environ is None else environ
    pidfile: Path | None = None
    run_id = str(getattr(issue, "active_run_id", "") or "")

    provider = getattr(issue, "resolved_provider", "") or config.pi_provider
    model = getattr(issue, "resolved_model", "") or config.pi_model
    # Remote PATH resolves the agent binary; the local absolute pi_bin path does
    # not exist on the remote, so dispatch by basename (probe confirmed `pi` is
    # on the remote PATH). A per-binding remote pi path is a future refinement.
    pi_name = Path(config.pi_bin).name or "pi"
    remote_skill_source = ""
    session_id = getattr(issue, "agent_session_id", "") or derive_session_id(issue.id)

    if skill_source:
        remote_skill_dir = f"{remote_tmp}/skill"
        skill_archive = _tar_directory_bytes(Path(skill_source).parent)
        ship_skill = run_func(
            _ssh_base_args(remote)
            + [
                f"mkdir -p {shlex.quote(remote_skill_dir)} && "
                f"tar -C {shlex.quote(remote_skill_dir)} -xf -"
            ],
            input=skill_archive,
            capture_output=True,
            check=False,
            timeout=PI_HELP_TIMEOUT_SECONDS,
        )
        if ship_skill.returncode != 0:
            _cleanup_remote_tmp(remote, remote_tmp, run_func=run_func)
            raise AgentRunnerError(
                f"Failed to ship skill to {remote.user}@{remote.host}: "
                f"{_stderr_text(ship_skill).strip()}"
            )
        remote_skill_source = f"{remote_skill_dir}/SKILL.md"

    pi_command = _build_pi_command(
        pi_name,
        provider,
        model,
        skill_source=remote_skill_source,
        session_id=session_id,
    )

    port = _remote_callback_port(config.plane_api_url)
    remote_command = _build_remote_command(
        repo_path=str(binding.repo_path),
        exports=_remote_exports(config, issue, binding=binding),
        pi_command=pi_command,
        helper_dir=remote_tmp if ship_plane_helper else "",
    )

    if ship_plane_helper:
        # 1. Ship the plane callback helper to the remote temp dir.
        ship = run_func(
            _ssh_base_args(remote)
            + [
                f"mkdir -p {shlex.quote(remote_tmp)} && cat > {shlex.quote(remote_tmp)}/plane "
                f"&& chmod 700 {shlex.quote(remote_tmp)}/plane"
            ],
            input=helper_text,
            capture_output=True,
            text=True,
            check=False,
            timeout=PI_HELP_TIMEOUT_SECONDS,
        )
        if ship.returncode != 0:
            _cleanup_remote_tmp(remote, remote_tmp, run_func=run_func)
            raise AgentRunnerError(
                f"Failed to ship plane helper to {remote.user}@{remote.host}: "
                f"{_stderr_text(ship).strip()}"
            )

    process: RpcProcessLike | None = None
    try:
        LOGGER.info(
            "remote_rpc_dispatch issue_id=%s host=%s repo=%s port=%s session_id=%s",
            issue.id,
            remote.host,
            binding.repo_path,
            port,
            session_id,
        )
        process = popen_factory(
            _ssh_base_args(remote, reverse_port=port) + [remote_command],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        with suppress(OSError):
            pid_dir = _rpc_pidfile_dir(source_env)
            pid_dir.mkdir(parents=True, exist_ok=True)
            pidfile = pid_dir / f"{process.pid}.pid"
            pidfile.write_text(pid_start_time(process.pid), encoding="utf-8")
        process.stdin.write(
            json.dumps({"type": "prompt", "message": rendered_prompt}) + "\n"
        )
        process.stdin.flush()

        deadline = started + (config.run_timeout_ms / 1000)
        steer_queue = import_module("web.api.steer_queue") if run_id else None
        read_queued_steers = steer_queue.read_steer_records if steer_queue else None
        read_line, close_reader = _rpc_line_reader(process)
        drain = _drain_rpc_events(
            process,
            deadline,
            run_id,
            read_queued_steers=read_queued_steers,
            steer_offset=0,
            read_line=read_line,
            close_reader=close_reader,
            kill_process_group=kill_process_group,
            clock=clock,
            source_env=source_env,
            spool_path=tail_spool_path(run_id, source_env) if run_id else None,
        )
        if drain.timed_out:
            duration_ms = int((clock() - started) * 1000)
            LOGGER.info(
                "agent_exited issue_id=%s exit_code=-1 duration_ms=%s timed_out=true remote=true",
                issue.id,
                duration_ms,
            )
            return AgentResult(
                -1,
                duration_ms,
                True,
                "".join(drain.assistant_parts),
                "".join(drain.stderr_parts),
            )

        try:
            process.wait(timeout=TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            _, stderr = _terminate_process_group(
                process,
                kill_process_group=kill_process_group,
            )
            if stderr:
                drain.stderr_parts.append(stderr)
        else:
            leftover_stderr = _read_remaining(process.stderr)
            if leftover_stderr:
                drain.stderr_parts.append(leftover_stderr)
        duration_ms = int((clock() - started) * 1000)
        exit_code = int(
            drain.event_exit_code
            if drain.event_exit_code is not None
            else (process.returncode or 0)
        )
        if drain.error_seen and exit_code == 0:
            exit_code = 1
        stdout = "".join(drain.assistant_parts)
        stderr = "".join(drain.stderr_parts)
        LOGGER.info(
            "agent_exited issue_id=%s exit_code=%s duration_ms=%s timed_out=false remote=true",
            issue.id,
            exit_code,
            duration_ms,
        )
        if drain.event_exit_code is None:
            silent_result = _silent_exit_result(
                issue_id=issue.id,
                exit_code=exit_code,
                duration_ms=duration_ms,
                stdout=stdout,
                stderr=stderr,
                message=(
                    "remote pi RPC exited 0 with empty stdout/stderr; treating as failure "
                    "because SSH closed before an agent_end event"
                ),
                log_event="remote_pi_silent_exit",
            )
            if silent_result is not None:
                return silent_result
        return AgentResult(exit_code, duration_ms, False, stdout, stderr)
    finally:
        if run_id:
            with suppress(Exception):
                import_module("web.api.steer_queue").clear_steer_queue(
                    run_id, environ=environ
                )
        if pidfile is not None:
            with suppress(OSError):
                pidfile.unlink(missing_ok=True)
        if run_id:
            with suppress(OSError):
                tail_spool_path(run_id, source_env).unlink(missing_ok=True)
        # Best-effort remote cleanup; the SSH channel close already SIGHUPs pi.
        _cleanup_remote_tmp(remote, remote_tmp, run_func=run_func)


def run_pi_rpc_agent(
    config: SymphonyConfig,
    issue: CandidateIssue,
    rendered_prompt: str,
    *,
    plane_cli_source: Path | None = None,
    popen_factory: Callable[..., RpcProcessLike] | None = None,
    mkdtemp: Callable[..., str] = tempfile.mkdtemp,
    copy_file: Callable[[Path, Path], object] = shutil.copy2,
    remove_tree: Callable[[str], object] = shutil.rmtree,
    kill_process_group: Callable[[int, int], object] = os.killpg,
    clock: Callable[[], float] = time.monotonic,
    environ: dict[str, str] | None = None,
) -> AgentResult:
    """Run pi in RPC mode and return the final assistant text as stdout."""

    helper_source = plane_cli_source or Path(__file__).with_name("plane_cli.py")
    if popen_factory is None:
        popen_factory = cast(Callable[..., RpcProcessLike], subprocess.Popen)
    temp_dir = mkdtemp(prefix="symphony-plane-cli-")
    started = clock()
    process: RpcProcessLike | None = None
    pidfile: Path | None = None
    run_id = str(getattr(issue, "active_run_id", "") or "")

    try:
        Path(temp_dir).mkdir(parents=True, exist_ok=True)
        if _uses_plane_tracker(config):
            helper_target = Path(temp_dir) / "plane"
            copy_file(helper_source, helper_target)
            helper_target.chmod(0o700)

        source_env = os.environ if environ is None else environ
        env = _agent_env(config, issue, temp_dir, source_env)
        provider = getattr(issue, "resolved_provider", "") or config.pi_provider
        model = getattr(issue, "resolved_model", "") or config.pi_model
        session_id = getattr(issue, "agent_session_id", "") or derive_session_id(
            issue.id
        )
        skill_source = getattr(issue, "skill_source", "")
        command = _build_pi_command(
            config.pi_bin,
            provider,
            model,
            skill_source=skill_source,
            session_id=session_id,
        )
        cwd = str(config.homelab_repo_path)
        LOGGER.info(
            "pi_rpc_dispatch issue_id=%s provider=%s model=%s session_id=%s cwd=%s",
            issue.id,
            provider,
            model,
            session_id,
            cwd,
        )
        process = popen_factory(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=cwd,
            start_new_session=True,
        )
        # Register the live process so a boot sweep can reap it if this scheduler
        # dies mid-run (the pi RPC child is its own session/group and would
        # otherwise linger). Best-effort: never let pidfile IO break dispatch.
        with suppress(OSError):
            pid_dir = _rpc_pidfile_dir(source_env)
            pid_dir.mkdir(parents=True, exist_ok=True)
            pidfile = pid_dir / f"{process.pid}.pid"
            # Record the process start-time so the boot reaper can tell our
            # orphan from a later process that reused the pid.
            pidfile.write_text(pid_start_time(process.pid), encoding="utf-8")
        process.stdin.write(
            json.dumps({"type": "prompt", "message": rendered_prompt}) + "\n"
        )
        process.stdin.flush()

        deadline = started + (config.run_timeout_ms / 1000)
        steer_queue = import_module("web.api.steer_queue") if run_id else None
        read_queued_steers = steer_queue.read_steer_records if steer_queue else None

        read_line, close_reader = _rpc_line_reader(process)
        drain = _drain_rpc_events(
            process,
            deadline,
            run_id,
            read_queued_steers=read_queued_steers,
            steer_offset=0,
            read_line=read_line,
            close_reader=close_reader,
            kill_process_group=kill_process_group,
            clock=clock,
            source_env=source_env,
        )
        if drain.timed_out:
            duration_ms = int((clock() - started) * 1000)
            return AgentResult(
                -1,
                duration_ms,
                True,
                "".join(drain.assistant_parts),
                "".join(drain.stderr_parts),
            )

        try:
            process.wait(timeout=TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            _, stderr = _terminate_process_group(
                process,
                kill_process_group=kill_process_group,
            )
            if stderr:
                drain.stderr_parts.append(stderr)
        else:
            leftover_stderr = _read_remaining(process.stderr)
            if leftover_stderr:
                drain.stderr_parts.append(leftover_stderr)
        duration_ms = int((clock() - started) * 1000)
        exit_code = int(
            drain.event_exit_code
            if drain.event_exit_code is not None
            else (process.returncode or 0)
        )
        if drain.error_seen and exit_code == 0:
            exit_code = 1
        return AgentResult(
            exit_code,
            duration_ms,
            False,
            "".join(drain.assistant_parts),
            "".join(drain.stderr_parts),
        )
    finally:
        if run_id:
            with suppress(Exception):
                import_module("web.api.steer_queue").clear_steer_queue(
                    run_id, environ=environ
                )
        if pidfile is not None:
            with suppress(OSError):
                pidfile.unlink(missing_ok=True)
        remove_tree(temp_dir)


@dataclass(frozen=True)
class PiRpcAgentAdapter:
    """Pi RPC subprocess adapter."""

    config: SymphonyConfig

    def __call__(self, issue: CandidateIssue, rendered_prompt: str, /) -> AgentResult:
        return run_pi_rpc_agent(self.config, issue, rendered_prompt)


def reap_orphan_rpc_processes(
    *,
    pidfile_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
    is_alive: Callable[[int], bool] | None = None,
    read_start_time: Callable[[int], str] | None = None,
    kill_group: Callable[[int, int], object] = os.killpg,
    glob_func: Callable[[Path], Iterable[Path]] | None = None,
    unlink_func: Callable[[Path], object] | None = None,
    clear_stale_queues: Callable[..., int] | None = None,
) -> int:
    """Kill orphan RPC process handles left behind by a prior scheduler.

    Boot-time sweep (#058 orphan reaping, the RPC analogue of
    ``reap_orphan_claude_sockets``). Every pidfile under ``<runtime>/rpc`` is
    from a previous instance — the current scheduler has not launched any RPC
    run yet. Local pi RPC runs record the pi process pid; remote RPC runs record
    the local SSH client pid, so killing it closes the channel and should SIGHUP
    the remote pi process. A pid is killed only when it is still alive AND its
    ``/proc/<pid>/stat`` start-time still matches the value recorded in the
    pidfile at launch; that start-time guard survives pid reuse and pi masking
    its own argv (its cmdline shows just ``pi``), which a cmdline check cannot.
    The pidfile is removed either way. The run reconciler independently fails
    the stale Run rows. Remote-side pi processes that survive SSH death remain
    outside the local boot sweep's reach.
    """
    alive_checker = is_alive or pid_alive
    start_time_reader = read_start_time or pid_start_time
    if unlink_func is None:
        unlink_func = _unlink_missing_ok
    if glob_func is None:
        glob_func = _default_pid_glob
    if pidfile_dir is None:
        pidfile_dir = _rpc_pidfile_dir(environ)
    clear_queue_files = clear_stale_queues
    if clear_queue_files is None:
        clear_queue_files = import_module(
            "web.api.steer_queue"
        ).clear_stale_steer_queues

    queue_count = clear_queue_files(environ=environ)
    count = 0
    if not pidfile_dir.exists():
        LOGGER.info("rpc_orphan_reap_done count=0 steer_queues=%d", queue_count)
        return 0
    for raw in glob_func(pidfile_dir):
        pidfile = Path(raw)
        try:
            pid = int(pidfile.stem)
        except ValueError:
            with suppress(OSError):
                unlink_func(pidfile)
            continue
        try:
            recorded = pidfile.read_text(encoding="utf-8").strip()
        except OSError:
            recorded = ""
        if recorded and alive_checker(pid) and start_time_reader(pid) == recorded:
            # SIGKILL, not SIGTERM: `pi --mode rpc` traps/ignores SIGTERM (it
            # reserves it for graceful RPC abort via stdin), so a leaderless
            # orphan never dies on TERM. The run reconciler has already failed
            # the Run row, so a hard kill of the leftover process is correct.
            with suppress(OSError, ProcessLookupError):
                kill_group(pid, signal.SIGKILL)
            LOGGER.info("rpc_orphan_reaped pid=%d", pid)
            count += 1
        with suppress(OSError, FileNotFoundError):
            unlink_func(pidfile)
    LOGGER.info("rpc_orphan_reap_done count=%d steer_queues=%d", count, queue_count)
    return count


def _unlink_missing_ok(path: Path) -> None:
    path.unlink(missing_ok=True)


def _default_pid_glob(directory: Path) -> Iterable[Path]:
    return sorted(directory.glob("*.pid"))


def verify_pi_rpc_support(
    pi_bin: str,
    cwd: Path | str,
    *,
    popen_factory: Callable[..., RpcProcessLike] | None = None,
    environ: Mapping[str, str] | None = None,
    timeout: float = PI_RPC_PROBE_TIMEOUT_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    kill_process_group: Callable[[int, int], object] = os.killpg,
) -> bool:
    """Confirm `pi --mode rpc` speaks the JSONL protocol, without an LLM call.

    Spawns the RPC process, sends ``get_state``, and waits for the matching
    ``response``. Non-fatal (#058 startup probe, analogue of
    ``verify_pi_support``): logs ``pi_rpc_probe_ok`` / ``pi_rpc_probe_failed``
    and returns a bool so a broken RPC binary surfaces at boot rather than on
    the first dispatch.
    """
    if popen_factory is None:
        popen_factory = cast(Callable[..., RpcProcessLike], subprocess.Popen)
    source_env = os.environ if environ is None else environ
    started = clock()
    process: RpcProcessLike | None = None
    try:
        process = popen_factory(
            [pi_bin, "--mode", "rpc", "--no-session"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=dict(source_env),
            cwd=str(cwd),
            start_new_session=True,
        )
        process.stdin.write(json.dumps({"type": "get_state"}) + "\n")
        process.stdin.flush()
        read_line, close_reader = _rpc_line_reader(process)
        deadline = started + timeout
        try:
            while True:
                remaining = deadline - clock()
                if remaining <= 0:
                    LOGGER.warning(
                        "pi_rpc_probe_failed reason=timeout after %gs", timeout
                    )
                    return False
                line, eof = read_line(remaining)
                if eof:
                    LOGGER.warning(
                        "pi_rpc_probe_failed reason=stream-closed-before-response"
                    )
                    return False
                if line is None:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    event.get("type") == "response"
                    and event.get("command") == "get_state"
                ):
                    if event.get("success"):
                        LOGGER.info("pi_rpc_probe_ok")
                        return True
                    LOGGER.warning(
                        "pi_rpc_probe_failed reason=%s",
                        event.get("error") or "get_state-unsuccessful",
                    )
                    return False
        finally:
            close_reader()
    except OSError as exc:
        LOGGER.warning("pi_rpc_probe_failed reason=%s", exc)
        return False
    finally:
        if process is not None:
            _send_rpc_abort(process)
            with suppress(Exception):
                _terminate_process_group(process, kill_process_group=kill_process_group)


@dataclass(frozen=True)
class PiAgentAdapter:
    """Pi one-shot subprocess adapter."""

    config: SymphonyConfig

    def __call__(self, issue: CandidateIssue, rendered_prompt: str, /) -> AgentResult:
        return run_agent(self.config, issue, rendered_prompt)


@dataclass(frozen=True)
class RemoteAgentAdapter:
    """Pi RPC adapter that dispatches over SSH to a remote host (ADR-0012)."""

    config: SymphonyConfig
    binding: ProjectBinding

    def __call__(self, issue: CandidateIssue, rendered_prompt: str, /) -> AgentResult:
        return run_remote_agent(
            self.config, issue, rendered_prompt, binding=self.binding
        )


@dataclass(frozen=True)
class RoutingAgentAdapter:
    """Route each issue to the agent resolved by its binding labels."""

    binding: ProjectBinding
    pi_adapter: AgentAdapter
    claude_adapter: AgentAdapter
    remote_adapter: AgentAdapter | None = None

    def __call__(self, issue: CandidateIssue, rendered_prompt: str, /) -> AgentResult:
        agent = self.binding.resolve_agent(issue.labels)
        pi_agent, claude_agent = KNOWN_AGENTS
        if self.binding.is_remote:
            if agent != pi_agent:
                raise AgentRunnerError(
                    f"Remote binding `{self.binding.name}` supports only pi dispatch "
                    f"in v1 (ADR-0012); got `{agent}`"
                )
            if self.remote_adapter is None:
                raise AgentRunnerError(
                    f"Remote binding `{self.binding.name}` has no remote adapter configured"
                )
            return self.remote_adapter(issue, rendered_prompt)
        if agent == pi_agent:
            return self.pi_adapter(issue, rendered_prompt)
        if agent == claude_agent:
            return self.claude_adapter(issue, rendered_prompt)
        raise AgentRunnerError(f"No agent adapter configured for `{agent}`")


def _drain_rpc_events(
    process: RpcProcessLike,
    deadline: float,
    run_id: str,
    *,
    read_queued_steers: SteerReader | None,
    steer_offset: int,
    read_line: Callable[[float], tuple[str | None, bool]],
    close_reader: Callable[[], None],
    kill_process_group: Callable[[int, int], object],
    clock: Callable[[], float],
    source_env: Mapping[str, str],
    spool_path: Path | None = None,
) -> _DrainResult:
    """Drain pi RPC JSONL events until timeout, agent_end, or error.

    Reads the event stream via the line reader, forwards steer records,
    and detects completion from ``agent_end`` events. The caller owns
    process termination for the non-timeout path. When ``spool_path`` is
    set, assistant deltas are mirrored to that local file so the web tailer
    can stream the run (used for remote dispatch — ADR-0019).
    """
    assistant_parts: list[str] = []
    stderr_parts: list[str] = []
    error_seen = False
    event_exit_code: int | None = None
    current_steer_offset = steer_offset

    spool = None
    spool_written = 0
    if spool_path is not None:
        with suppress(OSError):
            spool_path.parent.mkdir(parents=True, exist_ok=True)
            spool = spool_path.open("a", encoding="utf-8")

    try:
        while True:
            remaining = deadline - clock()
            if remaining <= 0:
                _send_rpc_abort(process)
                _, stderr = _terminate_process_group(
                    process,
                    kill_process_group=kill_process_group,
                )
                if stderr:
                    stderr_parts.append(stderr)
                return _DrainResult(
                    assistant_parts=assistant_parts,
                    stderr_parts=stderr_parts,
                    error_seen=error_seen,
                    event_exit_code=event_exit_code,
                    timed_out=True,
                    steer_offset=current_steer_offset,
                )

            if read_queued_steers is not None:
                steer_records, current_steer_offset = read_queued_steers(
                    run_id, current_steer_offset, environ=source_env
                )
                _forward_steer_records(process, steer_records)

            line, eof = read_line(min(remaining, RPC_STEER_POLL_INTERVAL_SECONDS))
            if eof:
                # stdout closed: process exited on its own (crash / fake).
                if process.poll() is not None:
                    event_exit_code = process.returncode
                break
            if line is None:
                continue  # no complete line within the poll window

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue  # banner / non-JSON noise on stdout

            event_type = str(event.get("type") or "")
            delta = _assistant_delta(event)
            if delta:
                assistant_parts.append(delta)
                if spool is not None:
                    with suppress(OSError):
                        spool.write(delta)
                        spool.flush()
                        spool_written += len(delta)
                        if spool_written >= TAIL_SPOOL_MAX_BYTES:
                            spool.write("\n[tail truncated — see run log for full output]\n")
                            spool.flush()
                            spool.close()
                            spool = None

            if event_type == "extension_error":
                err = event.get("error")
                if err:
                    stderr_parts.append(str(err))
            elif event_type == "response" and event.get("success") is False:
                # A rejected prompt yields no agent_end; fail fast.
                error_seen = True
                err = event.get("error")
                if err:
                    stderr_parts.append(str(err))
                if event.get("command") == "prompt":
                    break
            elif event_type == "message_update":
                ame = event.get("assistantMessageEvent")
                if (
                    isinstance(ame, dict)
                    and ame.get("type") == "error"
                    and ame.get("reason") != "aborted"
                ):
                    error_seen = True
                    reason = ame.get("reason") or ame.get("error")
                    if reason:
                        stderr_parts.append(str(reason))
            elif event_type == "agent_end":
                raw_code = event.get("exit_code", 0)
                try:
                    event_exit_code = int(raw_code)
                except (TypeError, ValueError):
                    event_exit_code = 0
                break
    finally:
        close_reader()
        if spool is not None:
            with suppress(OSError):
                spool.close()

    return _DrainResult(
        assistant_parts=assistant_parts,
        stderr_parts=stderr_parts,
        error_seen=error_seen,
        event_exit_code=event_exit_code,
        timed_out=False,
        steer_offset=current_steer_offset,
    )


@dataclass(frozen=True)
class _DrainResult:
    """Result of draining RPC events from a pi agent process."""

    assistant_parts: list[str]
    stderr_parts: list[str]
    error_seen: bool
    event_exit_code: int | None
    timed_out: bool
    steer_offset: int


def _close_rpc_stdin(process: RpcProcessLike) -> None:
    with suppress(Exception):
        process.stdin.close()


def _send_rpc_abort(process: RpcProcessLike) -> None:
    try:
        process.stdin.write(json.dumps({"type": "abort"}) + "\n")
        process.stdin.flush()
    except Exception:
        return


def _forward_steer_records(
    process: RpcProcessLike, records: Iterable[Mapping[str, object]]
) -> None:
    for record in records:
        kind = str(record.get("kind") or "")
        if kind == "abort":
            payload = {"type": "abort"}
        elif kind == "steer":
            message = str(record.get("message") or "").strip()
            if not message:
                continue
            payload = {"type": "steer", "message": message}
        else:
            continue
        try:
            process.stdin.write(json.dumps(payload) + "\n")
            process.stdin.flush()
        except Exception:
            return


def _rpc_line_reader(
    process: RpcProcessLike,
) -> tuple[Callable[[float], tuple[str | None, bool]], Callable[[], None]]:
    """Return ``(read_line, close)`` for pi's JSONL stdout.

    ``read_line(timeout)`` returns ``(line, eof)``: a complete LF-delimited line
    (with no trailing CR/LF) and ``eof=False``; ``(None, False)`` when no full
    line arrived within ``timeout``; ``(None, True)`` at stream end. Buffered
    lines are drained before the fd is polled again, so a terminal ``agent_end``
    sitting in the buffer is never stranded once pi goes idle. Reads the raw fd
    directly (not the buffered TextIO wrapper) to avoid a read-ahead split.
    A stream with no real fd (e.g. an ``io.StringIO`` test fake) falls back to
    synchronous ``readline``.
    """
    stdout = process.stdout
    try:
        fd = stdout.fileno()
    except (AttributeError, OSError, ValueError):
        fd = None

    if fd is None:

        def read_line(timeout: float) -> tuple[str | None, bool]:
            line = stdout.readline()
            if line == "":
                return None, True
            return line.rstrip("\r\n"), False

        return read_line, lambda: None

    selector = selectors.DefaultSelector()
    selector.register(fd, selectors.EVENT_READ)
    buf = bytearray()

    def read_line(timeout: float) -> tuple[str | None, bool]:
        while True:
            newline = buf.find(b"\n")
            if newline != -1:
                raw = bytes(buf[:newline])
                del buf[: newline + 1]
                return raw.decode("utf-8", "replace").rstrip("\r"), False
            if not selector.select(timeout=max(0.0, timeout)):
                return None, False
            data = os.read(fd, 65536)
            if data == b"":
                if buf:
                    raw = bytes(buf)
                    buf.clear()
                    return raw.decode("utf-8", "replace").rstrip("\r"), False
                return None, True
            buf.extend(data)

    return read_line, selector.close


def _assistant_delta(event: dict[str, object]) -> str:
    """Extract only streamed assistant text from a `message_update` event.

    Real pi nests it as `assistantMessageEvent.type == "text_delta"`; the
    simplified test fakes put a top-level `delta`. Thinking/tool-call deltas and
    every non-`message_update` event (extension banners, prompt echoes, status
    notifications) are excluded so they cannot pollute the SYMPHONY_RESULT scrape.
    """
    if event.get("type") != "message_update":
        return ""
    ame = event.get("assistantMessageEvent")
    if isinstance(ame, dict):
        if ame.get("type") == "text_delta":
            delta = ame.get("delta")
            return delta if isinstance(delta, str) else ""
        return ""
    delta = event.get("delta")
    return delta if isinstance(delta, str) else ""


def _read_remaining(stream: TextIOBase) -> str:
    try:
        return stream.read()
    except Exception:
        return ""


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
