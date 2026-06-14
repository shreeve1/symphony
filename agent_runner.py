"""Launch pi agents for Symphony issues."""

from __future__ import annotations

import json
import logging
import os
import re
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from io import TextIOBase
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from config import ProjectBinding, SymphonyConfig
from plane_poller import CandidateIssue
from session_continuity import derive_session_id


LOGGER = logging.getLogger(__name__)
TERMINATE_GRACE_SECONDS = 5
PI_HELP_TIMEOUT_SECONDS = 30
PI_PROBE_TIMEOUT_SECONDS = 30
PI_RPC_PROBE_TIMEOUT_SECONDS = 20
# Pidfile registry for live `pi --mode rpc` processes. Each dispatch writes
# <runtime_dir>/rpc/<pid>.pid on launch and removes it on exit; a boot sweep
# (reap_orphan_rpc_processes) kills any that a crashed scheduler left behind,
# the RPC analogue of reap_orphan_claude_sockets (#058 orphan reaping).
RPC_RUNTIME_DIR_ENV = "SYMPHONY_RUNTIME_DIR"
_DEFAULT_RUNTIME_DIR = Path("/tmp/symphony")
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _rpc_pidfile_dir(environ: Mapping[str, str] | None = None) -> Path:
    source = os.environ if environ is None else environ
    runtime_dir = Path(source.get(RPC_RUNTIME_DIR_ENV, str(_DEFAULT_RUNTIME_DIR)))
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


@dataclass(frozen=True)
class AgentResult:
    exit_code: int
    duration_ms: int
    timed_out: bool
    stdout: str = ""
    stderr: str = ""


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
            "SYMPHONY_PLANE_API_URL": config.plane_api_url,
            "SYMPHONY_PLANE_FRONTEND_URL": config.plane_frontend_url,
            "PLANE_DASHBOARD_URL": config.plane_dashboard_url,
            "SYMPHONY_PLANE_API_KEY": config.plane_api_key,
            "SYMPHONY_PLANE_PROJECT_ID": config.plane_project_id,
            "SYMPHONY_PLANE_WORKSPACE_SLUG": config.plane_workspace_slug,
            "PYTHONPATH": str(Path(__file__).parent),
        }
    )
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
    """Run pi for a Plane issue with a temporary Plane helper in PATH."""

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
        try:
            from web.api.worktree import create_worktree
        except ImportError:  # pragma: no cover - supports web/api import path
            from worktree import create_worktree  # type: ignore[no-redef]

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
        command = [
            config.pi_bin,
            "--print",
            "--no-session",
            "--provider",
            provider,
            "--model",
            model,
        ]
        skill_source = getattr(issue, "skill_source", "")
        if skill_source:
            # pi does not discover ~/.claude/skills on its own; load the
            # issue's preferred skill explicitly (directory form keeps any
            # skill assets alongside SKILL.md available).
            command += ["--skill", str(Path(skill_source).parent)]
        command.append(rendered_prompt)
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

    try:
        Path(temp_dir).mkdir(parents=True, exist_ok=True)
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
        command = [
            config.pi_bin,
            "--mode",
            "rpc",
            "--provider",
            provider,
            "--model",
            model,
            "--session-id",
            session_id,
        ]
        skill_source = getattr(issue, "skill_source", "")
        if skill_source:
            command += ["--skill", str(Path(skill_source).parent)]
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
            pidfile.write_text(_pid_start_time(process.pid), encoding="utf-8")
        process.stdin.write(
            json.dumps({"type": "prompt", "message": rendered_prompt}) + "\n"
        )
        process.stdin.flush()

        assistant_parts: list[str] = []
        stderr_parts: list[str] = []
        error_seen = False
        event_exit_code: int | None = None
        deadline = started + (config.run_timeout_ms / 1000)

        # pi RPC is a persistent session server: it streams its event burst then
        # stays alive idle, so stdout never reaches EOF on a normal completion.
        # The reader must therefore drain every buffered line on each poll and
        # detect completion from the `agent_end` event, never from EOF. (The old
        # selectors-on-fd + buffered-readline reader missed buffered lines once
        # the fd went quiet and spun to the timeout — see #050 / C-0188.)
        read_line, close_reader = _rpc_line_reader(process)
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
                    duration_ms = int((clock() - started) * 1000)
                    return AgentResult(
                        -1,
                        duration_ms,
                        True,
                        "".join(assistant_parts),
                        "".join(stderr_parts),
                    )

                line, eof = read_line(remaining)
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

        try:
            process.wait(timeout=TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            _, stderr = _terminate_process_group(
                process,
                kill_process_group=kill_process_group,
            )
            if stderr:
                stderr_parts.append(stderr)
        else:
            leftover_stderr = _read_remaining(process.stderr)
            if leftover_stderr:
                stderr_parts.append(leftover_stderr)
        duration_ms = int((clock() - started) * 1000)
        exit_code = int(
            event_exit_code
            if event_exit_code is not None
            else (process.returncode or 0)
        )
        if error_seen and exit_code == 0:
            exit_code = 1
        return AgentResult(
            exit_code,
            duration_ms,
            False,
            "".join(assistant_parts),
            "".join(stderr_parts),
        )
    finally:
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
) -> int:
    """Kill orphan `pi --mode rpc` processes left behind by a prior scheduler.

    Boot-time sweep (#058 orphan reaping, the RPC analogue of
    ``reap_orphan_claude_sockets``). Every pidfile under ``<runtime>/rpc`` is
    from a previous instance — the current scheduler has not launched any RPC
    run yet. A pid is killed only when it is still alive AND its
    ``/proc/<pid>/stat`` start-time still matches the value recorded in the
    pidfile at launch; that start-time guard survives pid reuse and pi masking
    its own argv (its cmdline shows just ``pi``), which a cmdline check cannot.
    The pidfile is removed either way. The run reconciler independently fails
    the stale Run rows, so this only cleans up leaked OS processes.
    """
    if is_alive is None:
        is_alive = _pid_alive
    if read_start_time is None:
        read_start_time = _pid_start_time
    if unlink_func is None:
        unlink_func = _unlink_missing_ok
    if glob_func is None:
        glob_func = _default_pid_glob
    if pidfile_dir is None:
        pidfile_dir = _rpc_pidfile_dir(environ)

    count = 0
    if not pidfile_dir.exists():
        LOGGER.info("rpc_orphan_reap_done count=0")
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
        if recorded and is_alive(pid) and read_start_time(pid) == recorded:
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
    LOGGER.info("rpc_orphan_reap_done count=%d", count)
    return count


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _pid_start_time(pid: int) -> str:
    """Return the process start-time (jiffies since boot) from /proc/<pid>/stat,
    or "" if unavailable. Used as a pid-reuse guard. Parses after the last ')'
    because the comm field can contain spaces and parens."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as handle:
            data = handle.read().decode("utf-8", "replace")
        fields = data[data.rindex(")") + 2 :].split()
        return fields[19]  # starttime: field 22 overall, index 19 after comm
    except (OSError, ValueError, IndexError):
        return ""


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
class RoutingAgentAdapter:
    """Route each issue to the agent resolved by its binding labels."""

    binding: ProjectBinding
    pi_adapter: AgentAdapter
    claude_adapter: AgentAdapter

    def __call__(self, issue: CandidateIssue, rendered_prompt: str, /) -> AgentResult:
        agent = self.binding.resolve_agent(issue.labels)
        if agent == "pi":
            return self.pi_adapter(issue, rendered_prompt)
        if agent == "claude":
            return self.claude_adapter(issue, rendered_prompt)
        raise AgentRunnerError(f"No agent adapter configured for `{agent}`")


def _send_rpc_abort(process: RpcProcessLike) -> None:
    try:
        process.stdin.write(json.dumps({"type": "abort"}) + "\n")
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


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", text)


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
