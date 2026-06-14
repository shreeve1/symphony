"""Launch Claude agents through an interactive tmux session."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from agent_runner import (
    _DEFAULT_RUNTIME_DIR,
    RPC_RUNTIME_DIR_ENV,
    AgentResult,
    AgentRunnerError,
    CompletedLike,
    _pid_alive,
    _pid_start_time,
    _strip_ansi,
)
from config import SymphonyConfig
from plane_poller import CandidateIssue
from session_continuity import derive_session_id, session_file_path


LOGGER = logging.getLogger(__name__)
READY_TIMEOUT_SECONDS = 30.0
CLAUDE_PROBE_TIMEOUT_SECONDS = 30.0
READY_PATTERN = "bypass permissions on|shift+tab to cycle"
# A large pasted prompt is not instantly settled in Claude's input box, so an
# Enter sent immediately after paste-buffer is sometimes absorbed into the paste
# and the prompt is never submitted (the pane keeps a `[Pasted text …]`
# placeholder). Settle before the first Enter, then re-send while the
# placeholder persists.
PASTE_SETTLE_SECONDS = 1.0
SUBMIT_RETRY_ATTEMPTS = 3
SUBMIT_RETRY_INTERVAL_SECONDS = 1.0
# Claude writes the result file then touches the done file as separate actions;
# poll a short grace window for the result to become non-empty before treating a
# done-but-empty result as a failure.
RESULT_GRACE_SECONDS = 3.0
RESULT_GRACE_STEP_SECONDS = 0.5
# When Claude ends its turn without performing the completion protocol it sits
# idle at the prompt: the tmux session stays alive and no done file ever lands,
# so the poll loop would otherwise wait out the full run_timeout_ms (an hour by
# default). Detect that stall by watching for the pane to stop changing -- while
# Claude is working its spinner/elapsed-timer redraws the pane at least once a
# second, so a pane that is byte-for-byte unchanged across this many 1s polls
# means the agent is parked. On idle, nudge it to complete the protocol a bounded
# number of times, then give up early rather than burning the full timeout.
IDLE_POLLS_BEFORE_NUDGE = 30
IDLE_NUDGE_ATTEMPTS = 2
_CLAUDE_PROBE_FAILURE_REASON: str | None = None


def claude_probe_failure_reason() -> str | None:
    """Return startup probe failure reason, if Claude dispatch is disabled."""

    return _CLAUDE_PROBE_FAILURE_REASON


def set_claude_probe_failure_reason(reason: str | None) -> None:
    """Set Claude probe state for startup wiring and tests."""

    global _CLAUDE_PROBE_FAILURE_REASON
    _CLAUDE_PROBE_FAILURE_REASON = reason


def verify_claude_support(
    *,
    run_func: Callable[..., CompletedLike] = subprocess.run,
    which_func: Callable[..., str | None] = shutil.which,
    environ: Mapping[str, str] | None = None,
    timeout: float = CLAUDE_PROBE_TIMEOUT_SECONDS,
) -> None:
    """Probe Claude CLI support without failing scheduler boot."""

    env = os.environ if environ is None else environ
    path = env.get("PATH")
    for binary in ("tmux", "claude"):
        if which_func(binary, path=path) is None:
            _record_claude_probe_failure(f"{binary} binary not found on PATH")
            return
    try:
        result = run_func(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=dict(env),
        )
    except subprocess.TimeoutExpired:
        _record_claude_probe_failure(f"claude --version timed out after {timeout:g}s")
        return
    except OSError as exc:
        _record_claude_probe_failure(f"claude --version could not run: {exc}")
        return
    if int(result.returncode) != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        detail = f": {stderr}" if stderr else ""
        _record_claude_probe_failure(
            f"claude --version failed with exit code {result.returncode}{detail}"
        )
        return
    set_claude_probe_failure_reason(None)
    LOGGER.info("claude_probe_ok")


def _record_claude_probe_failure(reason: str) -> None:
    set_claude_probe_failure_reason(reason)
    LOGGER.warning("claude_probe_failed reason=%s", reason)


def reap_orphan_claude_sockets(
    *,
    glob_func: Callable[[str], Iterable[str | Path]] | None = None,
    run_func: Callable[..., CompletedLike] = subprocess.run,
    unlink_func: Callable[[Path], object] | None = None,
    pidfile_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
    is_alive: Callable[[int], bool] | None = None,
    read_start_time: Callable[[int], str] | None = None,
) -> int:
    """Kill orphan Claude tmux servers left behind by prior scheduler runs.

    Ownership guard (the tmux-socket analogue of ``reap_orphan_rpc_processes``):
    each dispatch records a sidecar pidfile under ``<runtime>/claude`` naming the
    tmux server pid and its ``/proc/<pid>/stat`` start-time. A socket is reaped
    only when its recorded run is gone — the pidfile is missing, the server pid is
    dead, or the start-time no longer matches (pid reuse). A socket whose tmux
    server is still alive with a matching start-time is a LIVE run and is skipped.

    The guard is **best-effort and registration-dependent**: protection of a given
    run begins only once ``_register_claude_run`` has written its sidecar (the tmux
    server pid is only knowable after ``new-session`` returns), and a live socket
    whose registration failed or has not yet landed is indistinguishable from an
    orphan and would be reaped. The strong "never kills a live run" property in
    production rests on the call-site invariant — the reaper fires once at startup
    (``main.run_dispatcher``) before any dispatch, under the single-instance lock,
    so no live run exists at that moment — not on this guard alone. This guard is
    defence-in-depth atop that invariant, not a replacement for it.

    Stale-server sockets from a crashed prior run are still cleaned, preserving the
    boot-sweep purpose. A final pass also sweeps sidecar pidfiles whose run is gone
    (their socket may already have vanished), so sidecars cannot leak across boots
    if ``<runtime>`` is relocated off a ``PrivateTmp`` mount.
    """

    if glob_func is None:
        glob_func = _default_claude_socket_glob
    if unlink_func is None:
        unlink_func = _default_unlink
    if is_alive is None:
        is_alive = _pid_alive
    if read_start_time is None:
        read_start_time = _pid_start_time
    if pidfile_dir is None:
        pidfile_dir = _claude_pidfile_dir(environ)
    count = 0
    for raw_path in glob_func("/tmp/symphony-claude-*.sock"):
        socket_path = Path(raw_path)
        pidfile = pidfile_dir / f"{socket_path.stem}.pid"
        if _claude_run_owned_live(
            pidfile, is_alive=is_alive, read_start_time=read_start_time
        ):
            LOGGER.info("claude_socket_skipped_live path=%s", socket_path)
            continue
        with suppress(OSError):
            run_func(
                ["tmux", "-S", str(socket_path), "kill-server"],
                capture_output=True,
                text=True,
                check=False,
            )
        with suppress(OSError, FileNotFoundError):
            unlink_func(socket_path)
        LOGGER.info("claude_socket_reaped path=%s", socket_path)
        count += 1
    _sweep_orphan_claude_pidfiles(
        pidfile_dir,
        unlink_func=unlink_func,
        is_alive=is_alive,
        read_start_time=read_start_time,
    )
    LOGGER.info("claude_socket_reap_done count=%d", count)
    return count


def _sweep_orphan_claude_pidfiles(
    pidfile_dir: Path,
    *,
    unlink_func: Callable[[Path], object],
    is_alive: Callable[[int], bool],
    read_start_time: Callable[[int], str],
) -> None:
    """Unlink sidecar pidfiles whose recorded run is gone.

    Covers the reaped-socket sidecars and crash-leaked ones whose tmux server
    died (tmux removes the socket on crash, so the socket glob never sees them).
    A sidecar naming a still-live, matching run is kept.
    """
    if not pidfile_dir.exists():
        return
    for pidfile in sorted(pidfile_dir.glob("*.pid")):
        if _claude_run_owned_live(
            pidfile, is_alive=is_alive, read_start_time=read_start_time
        ):
            continue
        with suppress(OSError, FileNotFoundError):
            unlink_func(pidfile)


def _claude_pidfile_dir(environ: Mapping[str, str] | None = None) -> Path:
    source = os.environ if environ is None else environ
    runtime_dir = Path(source.get(RPC_RUNTIME_DIR_ENV, str(_DEFAULT_RUNTIME_DIR)))
    return runtime_dir / "claude"


def _claude_run_owned_live(
    pidfile: Path,
    *,
    is_alive: Callable[[int], bool],
    read_start_time: Callable[[int], str],
) -> bool:
    """True when the sidecar pidfile names a still-live, matching tmux server."""
    try:
        recorded = pidfile.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    parts = recorded.split()
    if len(parts) != 2:
        return False
    try:
        pid = int(parts[0])
    except ValueError:
        return False
    start_time = parts[1]
    return is_alive(pid) and read_start_time(pid) == start_time


def _claude_server_pid(
    socket_path: Path,
    session_name: str,
    *,
    run_func: Callable[..., CompletedLike],
) -> int | None:
    """Return the tmux server pid for a socket, or None if it cannot be read.

    tmux double-forks the server, so the ``new-session`` caller pid is not the
    server pid; ``display-message '#{pid}'`` queries the real server pid.
    """
    try:
        result = _tmux(
            run_func,
            socket_path,
            "display-message",
            "-p",
            "-t",
            session_name,
            "#{pid}",
        )
    except OSError:
        return None
    text = (result.stdout or "").strip()
    try:
        return int(text)
    except ValueError:
        return None


def _register_claude_run(
    socket_path: Path,
    session_name: str,
    *,
    run_func: Callable[..., CompletedLike],
    pidfile_dir: Path,
) -> Path | None:
    """Record a sidecar pidfile so the reaper can recognise this live run.

    Best-effort: never let pidfile IO break dispatch. The pidfile names the tmux
    server pid and its start-time; the boot reaper uses both to tell a live run
    from a stale socket (the start-time guard survives pid reuse).
    """
    server_pid = _claude_server_pid(socket_path, session_name, run_func=run_func)
    if server_pid is None:
        return None
    start_time = _pid_start_time(server_pid)
    if not start_time:
        return None
    pidfile = pidfile_dir / f"{socket_path.stem}.pid"
    with suppress(OSError):
        pidfile_dir.mkdir(parents=True, exist_ok=True)
        pidfile.write_text(f"{server_pid} {start_time}", encoding="utf-8")
        return pidfile
    return None


def _default_claude_socket_glob(pattern: str) -> Iterable[Path]:
    return Path("/tmp").glob(Path(pattern).name)


def _default_unlink(path: Path) -> None:
    path.unlink(missing_ok=True)


@dataclass
class ClaudeRunCleanup:
    """Idempotent cleanup for per-run tmux and filesystem artifacts."""

    socket_path: Path
    session_name: str
    temp_dir: Path
    run_func: Callable[..., CompletedLike] = subprocess.run
    remove_tree: Callable[[str], object] = shutil.rmtree
    pidfile_path: Path | None = None
    cleaned: bool = field(default=False, init=False)

    def cleanup(self) -> None:
        if self.cleaned:
            return
        self.cleaned = True
        with suppress(OSError):
            self.run_func(
                [
                    "tmux",
                    "-S",
                    str(self.socket_path),
                    "kill-session",
                    "-t",
                    self.session_name,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        with suppress(OSError):
            self.socket_path.unlink(missing_ok=True)
        if self.pidfile_path is not None:
            with suppress(OSError):
                self.pidfile_path.unlink(missing_ok=True)
        with suppress(FileNotFoundError):
            self.remove_tree(str(self.temp_dir))


@dataclass(frozen=True)
class ClaudeAgentAdapter:
    """Claude interactive tmux adapter."""

    config: SymphonyConfig

    def __call__(self, issue: CandidateIssue, rendered_prompt: str, /) -> AgentResult:
        return run_claude_agent(self.config, issue, rendered_prompt)


def run_claude_agent(
    config: SymphonyConfig,
    issue: CandidateIssue,
    rendered_prompt: str,
    *,
    run_func: Callable[..., CompletedLike] = subprocess.run,
    mkdtemp: Callable[..., str] = tempfile.mkdtemp,
    remove_tree: Callable[[str], object] = shutil.rmtree,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], object] = time.sleep,
    environ: dict[str, str] | None = None,
    nonce_factory: Callable[[], str] | None = None,
    create_worktree_func: Callable[[Path, str, str, str], Path] | None = None,
    ready_timeout_s: float = READY_TIMEOUT_SECONDS,
    pidfile_dir: Path | None = None,
    session_file: Path | None = None,
) -> AgentResult:
    """Run Claude for an issue using tmux send-keys and file completion."""

    model = getattr(issue, "resolved_model", "")
    if not model:
        raise AgentRunnerError("Claude dispatch requires issue.resolved_model")

    started = clock()
    nonce = (nonce_factory or (lambda: uuid.uuid4().hex[:12]))()
    namespace = f"symphony-claude-{issue.id}-{nonce}"
    temp_dir = Path(mkdtemp(prefix=f"{namespace}-"))
    socket_path = Path("/tmp") / f"{namespace}.sock"
    session_name = namespace
    prompt_file = temp_dir / "prompt.txt"
    result_file = temp_dir / "result.txt"
    done_file = temp_dir / "done"
    cleanup = ClaudeRunCleanup(
        socket_path, session_name, temp_dir, run_func, remove_tree
    )

    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        cwd = _resolve_cwd(config, issue, create_worktree_func=create_worktree_func)
        source_env = dict(os.environ) if environ is None else environ
        env = _claude_env(issue, source_env)
        session_id = getattr(issue, "agent_session_id", "") or derive_session_id(
            issue.id
        )
        resume_requested = bool(getattr(issue, "resumed", False))
        session_arg = "--resume" if resume_requested else "--session-id"
        transcript_file = session_file or session_file_path("claude", cwd, session_id)
        LOGGER.info(
            "claude_dispatch issue_id=%s model=%s cwd=%s session_id=%s resumed=%s",
            issue.id,
            model,
            cwd,
            session_id,
            str(resume_requested).lower(),
        )
        launch = run_func(
            [
                "tmux",
                "-S",
                str(socket_path),
                "new-session",
                "-d",
                "-s",
                session_name,
                "claude",
                "--permission-mode",
                "bypassPermissions",
                "--model",
                model,
                session_arg,
                session_id,
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd),
            env=env,
        )
        if int(launch.returncode) != 0:
            duration_ms = int((clock() - started) * 1000)
            stderr = _strip_ansi(f"{launch.stdout}\n{launch.stderr}".strip())
            return _logged_result(issue, 1, duration_ms, False, "", stderr)

        cleanup.pidfile_path = _register_claude_run(
            socket_path,
            session_name,
            run_func=run_func,
            pidfile_dir=pidfile_dir or _claude_pidfile_dir(source_env),
        )

        ready = _wait_until_ready(
            socket_path,
            session_name,
            run_func=run_func,
            clock=clock,
            sleep=sleep,
            timeout_s=ready_timeout_s,
        )
        if not ready:
            stderr = "claude_ready_timeout\n" + _capture_pane_tail(
                socket_path, session_name, run_func=run_func
            )
            duration_ms = int((clock() - started) * 1000)
            return _logged_result(issue, 1, duration_ms, False, "", stderr)

        prompt_file.write_text(
            _wrap_prompt(rendered_prompt, result_file, done_file, issue),
            encoding="utf-8",
        )
        _paste_and_submit(run_func, socket_path, session_name, prompt_file, sleep=sleep)

        deadline = started + (config.run_timeout_ms / 1000)
        last_pane: str | None = None
        last_mtime: float | None = None
        unchanged_polls = 0
        nudges_used = 0
        while clock() <= deadline:
            if done_file.exists():
                stdout = _read_result_with_grace(result_file, sleep=sleep)
                if not stdout.strip():
                    duration_ms = int((clock() - started) * 1000)
                    pane = _capture_pane_tail(
                        socket_path, session_name, run_func=run_func
                    )
                    stderr = (
                        "claude done file exists but result file is missing or "
                        f"empty after {RESULT_GRACE_SECONDS:g}s grace\n{pane}"
                    )
                    return _logged_result(issue, 137, duration_ms, False, "", stderr)
                stderr = _capture_pane_full(
                    socket_path, session_name, run_func=run_func
                )
                duration_ms = int((clock() - started) * 1000)
                return _logged_result(issue, 0, duration_ms, False, stdout, stderr)
            if not _session_alive(socket_path, session_name, run_func=run_func):
                duration_ms = int((clock() - started) * 1000)
                stderr = _capture_pane_tail(
                    socket_path, session_name, run_func=run_func
                )
                return _logged_result(issue, 1, duration_ms, False, "", stderr)
            # Idle requires BOTH the pane and the agent's session transcript to
            # stop changing. The two signals are complementary: a long tool call
            # leaves the transcript static but the pane's spinner/timer still
            # redrawing, while an alt-screen pane that captures empty leaves the
            # transcript still being appended. Treating activity on either channel
            # as "not idle" stops a working agent from being nudged or killed. A
            # missing transcript (mtime is None) counts as activity, never idle.
            pane = _capture_pane_full(socket_path, session_name, run_func=run_func)
            mtime = _session_file_mtime(transcript_file)
            if mtime is not None and pane == last_pane and mtime == last_mtime:
                unchanged_polls += 1
            else:
                unchanged_polls = 0
                last_pane = pane
                last_mtime = mtime
            if unchanged_polls >= IDLE_POLLS_BEFORE_NUDGE:
                if nudges_used >= IDLE_NUDGE_ATTEMPTS:
                    duration_ms = int((clock() - started) * 1000)
                    tail = _capture_pane_tail(
                        socket_path, session_name, run_func=run_func
                    )
                    stderr = (
                        "claude idle at prompt with no done file after "
                        f"{IDLE_NUDGE_ATTEMPTS} completion nudges; agent ended its "
                        "turn without completing the Symphony completion "
                        f"protocol\n{tail}"
                    )
                    LOGGER.info(
                        "claude_idle_no_completion issue_id=%s nudges=%s "
                        "duration_ms=%s",
                        issue.id,
                        nudges_used,
                        duration_ms,
                    )
                    return _logged_result(issue, -1, duration_ms, True, "", stderr)
                _send_nudge(
                    run_func,
                    socket_path,
                    session_name,
                    prompt_file,
                    result_file,
                    done_file,
                    sleep=sleep,
                )
                nudges_used += 1
                unchanged_polls = 0
                last_pane = None
                last_mtime = None
                LOGGER.info(
                    "claude_idle_nudge issue_id=%s nudge=%s", issue.id, nudges_used
                )
            sleep(1.0)

        duration_ms = int((clock() - started) * 1000)
        stderr = _capture_pane_tail(socket_path, session_name, run_func=run_func)
        return _logged_result(issue, -1, duration_ms, True, "", stderr)
    finally:
        cleanup.cleanup()


def _resolve_cwd(
    config: SymphonyConfig,
    issue: CandidateIssue,
    *,
    create_worktree_func: Callable[[Path, str, str, str], Path] | None,
) -> Path:
    if getattr(issue, "worktree_active", False):
        if create_worktree_func is None:
            try:
                from web.api.worktree import create_worktree
            except ImportError:  # pragma: no cover - supports web/api import path
                from worktree import create_worktree  # type: ignore[no-redef]
            create_worktree_func = create_worktree
        binding_name = getattr(issue, "binding_name", "") or (
            config.bindings[0].name if config.bindings else ""
        )
        base_branch = getattr(issue, "base_branch", "") or config.base_branch or "main"
        return create_worktree_func(
            config.homelab_repo_path, binding_name, issue.id, base_branch
        )
    return config.homelab_repo_path


def _claude_env(issue: CandidateIssue, source_env: Mapping[str, str]) -> dict[str, str]:
    allowed = {"PATH", "HOME", "USER", "LANG", "TMPDIR", "XDG_RUNTIME_DIR"}
    env = {key: value for key, value in source_env.items() if key in allowed}
    env["SYMPHONY_ISSUE_ID"] = issue.id
    return env


def _wrap_prompt(
    rendered_prompt: str,
    result_file: Path,
    done_file: Path,
    issue: CandidateIssue,
) -> str:
    skill = getattr(issue, "preferred_skill", None)
    skill_directive = (
        f"\nInvoke the `{skill}` skill by name before doing the work." if skill else ""
    )
    return f"""You are running unattended for Symphony. Nobody can respond live.
If you need operator clarification, park the turn with the `SYMPHONY_QUESTION_BEGIN`/`SYMPHONY_QUESTION_END` protocol from the rendered Symphony output contract. If genuinely blocked on an error, still complete the two steps below with `SYMPHONY_RESULT: blocked` as the result content.{skill_directive}

Completion protocol — follow exactly, in order:
1. Write your full final output — either the `SYMPHONY_RESULT` line plus the `SYMPHONY_SUMMARY_BEGIN`/`SYMPHONY_SUMMARY_END` block, or the `SYMPHONY_QUESTION_BEGIN`/`SYMPHONY_QUESTION_END` block described in the Symphony output contract below — to this literal result file path:
{result_file}
   Use your file-writing (Write) tool, NOT a shell heredoc or `cat <<EOF`, so backticks and other shell-special characters in your summary are written literally and the write cannot be broken by the shell.
2. Confirm the result file exists and is non-empty (e.g. `test -s {result_file}`).
3. ONLY after that confirmation, create this literal done file path:
{done_file}
   This done file signals completion. Do NOT create it if the result file is missing or empty — an empty result is treated as a failed run.

Rendered issue prompt follows unchanged:

{rendered_prompt}
"""


def _wait_until_ready(
    socket_path: Path,
    session_name: str,
    *,
    run_func: Callable[..., CompletedLike],
    clock: Callable[[], float],
    sleep: Callable[[float], object],
    timeout_s: float,
) -> bool:
    deadline = clock() + timeout_s
    while clock() <= deadline:
        pane = _capture_pane_full(socket_path, session_name, run_func=run_func)
        if _ready_pattern_seen(pane):
            return True
        sleep(0.5)
    return False


def _ready_pattern_seen(text: str) -> bool:
    lowered = text.lower()
    return "bypass permissions on" in lowered or "shift+tab to cycle" in lowered


def _tmux(
    run_func: Callable[..., CompletedLike], socket_path: Path, *args: str
) -> CompletedLike:
    return run_func(
        ["tmux", "-S", str(socket_path), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _capture_pane_full(
    socket_path: Path,
    session_name: str,
    *,
    run_func: Callable[..., CompletedLike],
) -> str:
    try:
        result = _tmux(run_func, socket_path, "capture-pane", "-pt", session_name)
    except OSError:
        return ""
    return _strip_ansi(result.stdout or result.stderr or "")


def _capture_pane_tail(
    socket_path: Path,
    session_name: str,
    *,
    run_func: Callable[..., CompletedLike],
) -> str:
    try:
        result = _tmux(
            run_func, socket_path, "capture-pane", "-pt", session_name, "-S", "-200"
        )
    except OSError:
        return ""
    return _strip_ansi(result.stdout or result.stderr or "")


def _paste_and_submit(
    run_func: Callable[..., CompletedLike],
    socket_path: Path,
    session_name: str,
    prompt_file: Path,
    *,
    sleep: Callable[[float], object],
) -> None:
    """Paste the prompt and submit it, tolerating the tmux paste/Enter race.

    Settle after paste-buffer before the first Enter, then re-send Enter while
    the pane still shows the unsubmitted `[Pasted text …]` placeholder (up to
    ``SUBMIT_RETRY_ATTEMPTS``). Once the placeholder clears, the prompt was
    submitted; a stray Enter on the already-submitted prompt is harmless.
    """
    _tmux(run_func, socket_path, "load-buffer", str(prompt_file))
    _tmux(run_func, socket_path, "paste-buffer", "-t", session_name)
    sleep(PASTE_SETTLE_SECONDS)
    for _ in range(SUBMIT_RETRY_ATTEMPTS):
        _tmux(run_func, socket_path, "send-keys", "-t", session_name, "Enter")
        sleep(SUBMIT_RETRY_INTERVAL_SECONDS)
        pane = _capture_pane_full(socket_path, session_name, run_func=run_func)
        if not _paste_pending(pane):
            return


def _paste_pending(pane: str) -> bool:
    """True when the pane still shows an unsubmitted pasted-prompt placeholder."""
    return "pasted text" in pane.lower()


def _nudge_text(result_file: Path, done_file: Path) -> str:
    """Reminder pasted into an idle session to finish the completion protocol."""
    return (
        "You appear to have stopped without completing the Symphony completion "
        "protocol. Nobody can respond live. Finish now, in order:\n"
        "1. Use your Write tool to write your full final output (the "
        "SYMPHONY_RESULT line plus the SYMPHONY_SUMMARY_BEGIN/SYMPHONY_SUMMARY_END "
        "block, or a SYMPHONY_QUESTION_BEGIN/SYMPHONY_QUESTION_END block) to this "
        f"literal result file path: {result_file}\n"
        f"2. Confirm the result file exists and is non-empty (test -s {result_file}).\n"
        f"3. ONLY after that confirmation, create this literal done file path: "
        f"{done_file}\n"
        "Do NOT create the done file if the result file is missing or empty."
    )


def _send_nudge(
    run_func: Callable[..., CompletedLike],
    socket_path: Path,
    session_name: str,
    prompt_file: Path,
    result_file: Path,
    done_file: Path,
    *,
    sleep: Callable[[float], object],
) -> None:
    """Paste a completion-protocol reminder into an idle session and submit it.

    Reuses ``_paste_and_submit`` so the same paste/Enter race handling applies.
    The idle input box is empty, so the reminder is submitted as a fresh turn.
    """
    prompt_file.write_text(_nudge_text(result_file, done_file), encoding="utf-8")
    _paste_and_submit(run_func, socket_path, session_name, prompt_file, sleep=sleep)


def _read_result_with_grace(
    result_file: Path,
    *,
    sleep: Callable[[float], object],
    grace_s: float = RESULT_GRACE_SECONDS,
    step_s: float = RESULT_GRACE_STEP_SECONDS,
) -> str:
    """Read the result file, re-polling a short grace window for it to fill.

    The agent writes the result file and touches the done file as separate
    steps, so the result can lag the done marker by a beat. Returns the result
    text as soon as it is non-empty, or the final (possibly empty) read after
    the grace window. Iteration-bounded so it terminates under a frozen clock.
    """
    steps = max(1, int(grace_s / step_s))
    for _ in range(steps):
        if result_file.exists():
            text = result_file.read_text(encoding="utf-8")
            if text.strip():
                return text
        sleep(step_s)
    return result_file.read_text(encoding="utf-8") if result_file.exists() else ""


def _session_file_mtime(path: Path) -> float | None:
    """Modification time of the agent's session transcript, or None if absent.

    Claude appends to this jsonl on every conversation event, so an advancing
    mtime means the agent is actively producing output; a frozen mtime is the
    ground-truth idle signal that the pane-stability check is gated against.
    """
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _session_alive(
    socket_path: Path,
    session_name: str,
    *,
    run_func: Callable[..., CompletedLike],
) -> bool:
    try:
        result = _tmux(run_func, socket_path, "has-session", "-t", session_name)
    except OSError:
        return False
    return int(result.returncode) == 0


def _logged_result(
    issue: CandidateIssue,
    exit_code: int,
    duration_ms: int,
    timed_out: bool,
    stdout: str,
    stderr: str,
) -> AgentResult:
    LOGGER.info(
        "agent_exited issue_id=%s exit_code=%s duration_ms=%s timed_out=%s",
        issue.id,
        exit_code,
        duration_ms,
        str(timed_out).lower(),
    )
    return AgentResult(exit_code, duration_ms, timed_out, stdout, stderr)
