"""Launch Claude agents through an interactive tmux session."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

from agent_runner import AgentResult, AgentRunnerError, CompletedLike
from config import SymphonyConfig
from proc_runtime import (
    DEFAULT_RUNTIME_DIR,
    RPC_RUNTIME_DIR_ENV,
    pid_alive,
    pid_start_time,
    strip_ansi,
)
from plane_poller import CandidateIssue
from session_continuity import derive_session_id, session_file_path


LOGGER = logging.getLogger(__name__)
READY_TIMEOUT_SECONDS = 30.0
CLAUDE_PROBE_TIMEOUT_SECONDS = 30.0
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
# A parked pane can be a Claude permission prompt rather than an ended turn:
# ``--permission-mode bypassPermissions`` does NOT suppress confirmation modals
# for edits under ``.claude/`` (Claude's own settings/skills), so an agent that
# touches those files hangs on an unanswerable modal until the run times out and
# is mislabelled "Agent timed out." When an idle pane matches a permission modal,
# send Escape to reject it (giving the agent a chance to recover and complete);
# if it keeps reappearing after this many rejections, abort with a clear reason
# instead of nudging.
MODAL_DISMISS_ATTEMPTS = 2
# A Claude permission modal shows a numbered Yes/No choice list plus an
# escape/confirm hint footer; require both so ordinary agent output never matches.
_MODAL_CHOICE_RE = re.compile(r"(?im)^\s*(?:❯\s*)?\d+\.\s+(?:Yes|No)\b")
_MODAL_HINT_RE = re.compile(
    r"(?i)\besc to (?:cancel|reject|interrupt)\b"
    r"|do you want to (?:make this edit|proceed|create|run|allow)"
)
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
    lock_confirmed: bool = False,
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

    Persistent Claude sockets are scheduler-lifetime warm sessions only. On boot,
    when the caller has confirmed the single-instance scheduler lock is held,
    persistent sockets bypass the pidfile guard and are killed so a restart starts
    cold and resumes from Claude's transcript instead of reattaching to a detached
    pre-restart tmux server. If lock ownership is not confirmed, persistent sockets
    use the same pid/start-time guard as nonce sockets; leaking a stale warm socket
    is safer than killing a live peer scheduler's session.

    The guard is **best-effort and registration-dependent**: protection of a given
    run begins only once ``_register_claude_run`` has written its sidecar (the tmux
    server pid is only knowable after ``new-session`` returns), and a live socket
    whose registration failed or has not yet landed is indistinguishable from an
    orphan and would be reaped. The strong "never kills a live run" property in
    production rests on the call-site invariant — the reaper fires once at startup
    before any dispatch, under the single-instance lock — not on this guard alone.
    This guard is defence-in-depth atop that invariant, not a replacement for it.

    Stale-server sockets from a crashed prior run are still cleaned, preserving the
    boot-sweep purpose. A final pass also sweeps sidecar pidfiles whose run is gone
    (their socket may already have vanished), so sidecars cannot leak across boots
    if ``<runtime>`` is relocated off a ``PrivateTmp`` mount.
    """

    if glob_func is None:
        glob_func = _default_claude_socket_glob
    if unlink_func is None:
        unlink_func = _default_unlink
    alive_checker = is_alive or pid_alive
    start_time_reader = read_start_time or pid_start_time
    if pidfile_dir is None:
        pidfile_dir = _claude_pidfile_dir(environ)
    force_unlinked_pidfiles: set[Path] = set()
    count = 0
    for raw_path in glob_func("/tmp/symphony-claude-*.sock"):
        socket_path = Path(raw_path)
        pidfile = pidfile_dir / f"{socket_path.stem}.pid"
        bypass_guard = lock_confirmed and _is_persistent_claude_socket(socket_path)
        if not bypass_guard and _claude_run_owned_live(
            pidfile, is_alive=alive_checker, read_start_time=start_time_reader
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
        if bypass_guard:
            with suppress(OSError, FileNotFoundError):
                unlink_func(pidfile)
            force_unlinked_pidfiles.add(pidfile)
        LOGGER.info("claude_socket_reaped path=%s", socket_path)
        count += 1
    _sweep_orphan_claude_pidfiles(
        pidfile_dir,
        unlink_func=unlink_func,
        is_alive=alive_checker,
        read_start_time=start_time_reader,
        skip_pidfiles=force_unlinked_pidfiles,
    )
    LOGGER.info("claude_socket_reap_done count=%d", count)
    return count


def _sweep_orphan_claude_pidfiles(
    pidfile_dir: Path,
    *,
    unlink_func: Callable[[Path], object],
    is_alive: Callable[[int], bool],
    read_start_time: Callable[[int], str],
    skip_pidfiles: set[Path] | None = None,
) -> None:
    """Unlink sidecar pidfiles whose recorded run is gone.

    Covers the reaped-socket sidecars and crash-leaked ones whose tmux server
    died (tmux removes the socket on crash, so the socket glob never sees them).
    A sidecar naming a still-live, matching run is kept.
    """
    if not pidfile_dir.exists():
        return
    skipped = skip_pidfiles or set()
    for pidfile in sorted(pidfile_dir.glob("*.pid")):
        if pidfile in skipped:
            continue
        if _claude_run_owned_live(
            pidfile, is_alive=is_alive, read_start_time=read_start_time
        ):
            continue
        with suppress(OSError, FileNotFoundError):
            unlink_func(pidfile)


def _claude_pidfile_dir(environ: Mapping[str, str] | None = None) -> Path:
    source = os.environ if environ is None else environ
    runtime_dir = Path(source.get(RPC_RUNTIME_DIR_ENV, str(DEFAULT_RUNTIME_DIR)))
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
    start_time = pid_start_time(server_pid)
    if not start_time:
        return None
    pidfile = pidfile_dir / f"{socket_path.stem}.pid"
    with suppress(OSError):
        pidfile_dir.mkdir(parents=True, exist_ok=True)
        pidfile.write_text(f"{server_pid} {start_time}", encoding="utf-8")
        return pidfile
    return None


def _persistent_session_live(
    socket_path: Path,
    session_name: str,
    *,
    run_func: Callable[..., CompletedLike],
) -> bool:
    """True when a persistent tmux socket/session/server is safe to reuse."""

    if not socket_path.exists():
        return False
    if not _session_alive(socket_path, session_name, run_func=run_func):
        return False
    server_pid = _claude_server_pid(socket_path, session_name, run_func=run_func)
    return server_pid is not None and pid_alive(server_pid)


def _cleanup_claude_session_artifacts(
    socket_path: Path,
    session_name: str,
    *,
    run_func: Callable[..., CompletedLike],
    pidfile_path: Path | None = None,
    metadata_path: Path | None = None,
) -> None:
    """Best-effort cleanup for a stale reusable Claude session."""

    with suppress(OSError):
        run_func(
            [
                "tmux",
                "-S",
                str(socket_path),
                "kill-session",
                "-t",
                session_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    with suppress(OSError):
        socket_path.unlink(missing_ok=True)
    if pidfile_path is not None:
        with suppress(OSError):
            pidfile_path.unlink(missing_ok=True)
    if metadata_path is not None:
        with suppress(OSError):
            metadata_path.unlink(missing_ok=True)


def _default_claude_socket_glob(pattern: str) -> Iterable[Path]:
    return Path("/tmp").glob(Path(pattern).name)


def _default_unlink(path: Path) -> None:
    path.unlink(missing_ok=True)


_PERSISTENT_SOCKET_PREFIX = "symphony-claude-persist-"


def _is_persistent_claude_socket(path: Path) -> bool:
    return path.stem.startswith(_PERSISTENT_SOCKET_PREFIX)


def _sanitize_socket_component(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-.")
    return sanitized or "unknown"


def persistent_socket_path(binding: str, issue_id: str) -> Path:
    """Return the deterministic tmux socket for a reusable Claude session."""

    safe_binding = _sanitize_socket_component(binding)
    safe_issue = _sanitize_socket_component(issue_id)
    return Path("/tmp") / f"{_PERSISTENT_SOCKET_PREFIX}{safe_binding}-{safe_issue}.sock"


def issue_id_from_persistent_socket(path: str | Path) -> str | None:
    """Best-effort issue id extraction from a persistent Claude socket path."""

    stem = Path(path).stem
    if not stem.startswith(_PERSISTENT_SOCKET_PREFIX):
        return None
    suffix = stem.removeprefix(_PERSISTENT_SOCKET_PREFIX)
    if "-" not in suffix:
        return None
    issue_id = suffix.rsplit("-", 1)[1]
    return issue_id or None


def _issue_binding_name(config: SymphonyConfig, issue: CandidateIssue) -> str:
    return getattr(issue, "binding_name", "") or (
        config.bindings[0].name if config.bindings else "default"
    )


def _write_claude_session_metadata(
    path: Path,
    *,
    issue_id: str,
    binding: str,
    cwd: Path,
    session_file: Path,
    session_name: str,
) -> Path | None:
    payload = {
        "issue_id": issue_id,
        "binding": binding,
        "cwd": str(cwd),
        "session_file": str(session_file),
        "session_name": session_name,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        LOGGER.warning("claude_metadata_write_failed path=%s error=%s", path, exc)
        return None
    return path


def sweep_persistent_claude_sessions(
    binding: str,
    *,
    get_issue: Callable[[str], Any],
    now: float,
    idle_ttl_s: float,
    max_live: int,
) -> int:
    """Reap parked persistent Claude sessions for one binding.

    The metadata sidecar is the authoritative issue/cwd/transcript source.
    Socket-name issue extraction is only a fallback because sanitized names are
    lossy and can collide.
    """

    pidfile_dir = _claude_pidfile_dir()
    safe_binding = _sanitize_socket_component(binding)
    parked: list[tuple[float, str, Path, str, Path, Path]] = []
    reaped = 0
    for raw_path in _default_claude_socket_glob(
        f"/tmp/{_PERSISTENT_SOCKET_PREFIX}{safe_binding}-*.sock"
    ):
        socket_path = Path(raw_path)
        metadata_path = pidfile_dir / f"{socket_path.stem}.meta.json"
        pidfile_path = pidfile_dir / f"{socket_path.stem}.pid"
        metadata = _read_claude_session_metadata(metadata_path)
        fallback_issue_id = issue_id_from_persistent_socket(socket_path)
        issue_id = _metadata_string(metadata, "issue_id") or fallback_issue_id
        metadata_binding = _metadata_string(metadata, "binding")
        if metadata_binding and metadata_binding != binding:
            LOGGER.warning(
                "claude_persist_metadata_binding_mismatch socket=%s metadata_binding=%s binding=%s",
                socket_path,
                metadata_binding,
                binding,
            )
        if metadata and fallback_issue_id and issue_id != fallback_issue_id:
            LOGGER.warning(
                "claude_persist_socket_issue_mismatch socket=%s metadata_issue_id=%s socket_issue_id=%s",
                socket_path,
                issue_id,
                fallback_issue_id,
            )
        session_name = _metadata_string(metadata, "session_name") or socket_path.stem
        live = _session_alive(socket_path, session_name, run_func=subprocess.run)
        if metadata is None and not live:
            _cleanup_claude_session_artifacts(
                socket_path,
                session_name,
                run_func=subprocess.run,
                pidfile_path=pidfile_path,
                metadata_path=metadata_path,
            )
            LOGGER.info("claude_persist_orphan_reaped socket=%s", socket_path)
            reaped += 1
            continue
        if not issue_id:
            LOGGER.warning("claude_persist_missing_issue_id socket=%s", socket_path)
            continue

        issue = get_issue(issue_id)
        state = _issue_attr(issue, "state")
        latest_run_state = _issue_attr(issue, "latest_run_state")
        if state == "running" and latest_run_state == "running":
            LOGGER.info("claude_persist_reap_skip_running issue_id=%s", issue_id)
            continue
        if issue is None or state in {"done", "archived"}:
            _cleanup_claude_session_artifacts(
                socket_path,
                session_name,
                run_func=subprocess.run,
                pidfile_path=pidfile_path,
                metadata_path=metadata_path,
            )
            LOGGER.info(
                "claude_persist_terminal_reaped issue_id=%s state=%s", issue_id, state
            )
            reaped += 1
            continue

        transcript_path = _metadata_path(metadata, "session_file")
        mtime = _path_mtime(transcript_path) if transcript_path else None
        if mtime is not None and now - mtime > idle_ttl_s:
            _cleanup_claude_session_artifacts(
                socket_path,
                session_name,
                run_func=subprocess.run,
                pidfile_path=pidfile_path,
                metadata_path=metadata_path,
            )
            LOGGER.info(
                "claude_persist_idle_reaped issue_id=%s idle_s=%s",
                issue_id,
                int(now - mtime),
            )
            reaped += 1
            continue
        parked.append(
            (
                mtime if mtime is not None else float("inf"),
                issue_id,
                socket_path,
                session_name,
                pidfile_path,
                metadata_path,
            )
        )

    live_cap = max(0, int(max_live))
    if len(parked) > live_cap:
        to_reap = sorted(parked, key=lambda item: item[0])[: len(parked) - live_cap]
        for (
            _mtime,
            issue_id,
            socket_path,
            session_name,
            pidfile_path,
            metadata_path,
        ) in to_reap:
            _cleanup_claude_session_artifacts(
                socket_path,
                session_name,
                run_func=subprocess.run,
                pidfile_path=pidfile_path,
                metadata_path=metadata_path,
            )
            reaped += 1
        LOGGER.info(
            "claude_persist_max_live_reaped count=%s issue_ids=%s",
            len(to_reap),
            ",".join(issue_id for _, issue_id, *_ in to_reap),
        )
    return reaped


def _read_claude_session_metadata(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _metadata_string(metadata: Mapping[str, Any] | None, key: str) -> str | None:
    if metadata is None:
        return None
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


def _metadata_path(metadata: Mapping[str, Any] | None, key: str) -> Path | None:
    value = _metadata_string(metadata, key)
    return Path(value) if value else None


def _issue_attr(issue: Any, key: str) -> Any:
    if issue is None:
        return None
    if isinstance(issue, Mapping):
        return issue.get(key)
    return getattr(issue, key, None)


def _path_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


@dataclass
class ClaudeRunCleanup:
    """Idempotent cleanup for per-run and per-session Claude artifacts."""

    socket_path: Path
    session_name: str
    temp_dir: Path
    run_func: Callable[..., CompletedLike] = subprocess.run
    remove_tree: Callable[[str], object] = shutil.rmtree
    pidfile_path: Path | None = None
    metadata_path: Path | None = None
    run_cleaned: bool = field(default=False, init=False)
    session_cleaned: bool = field(default=False, init=False)

    def cleanup_run(self) -> None:
        """Remove only per-run temporary files."""

        if self.run_cleaned:
            return
        self.run_cleaned = True
        with suppress(FileNotFoundError):
            self.remove_tree(str(self.temp_dir))

    def cleanup_session(self) -> None:
        """Tear down the tmux session and session-scoped sidecars."""

        if self.session_cleaned:
            return
        self.session_cleaned = True
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
        if self.metadata_path is not None:
            with suppress(OSError):
                self.metadata_path.unlink(missing_ok=True)

    def cleanup(self) -> None:
        """Preserve the historical combined cleanup behavior."""

        self.cleanup_session()
        self.cleanup_run()


@dataclass(frozen=True)
class ClaudeAgentAdapter:
    """Claude interactive tmux adapter."""

    config: SymphonyConfig
    persist: bool = False

    def __call__(self, issue: CandidateIssue, rendered_prompt: str, /) -> AgentResult:
        return run_claude_agent(
            self.config, issue, rendered_prompt, persist=self.persist
        )


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
    persist: bool = False,
) -> AgentResult:
    """Run Claude for an issue using tmux send-keys and file completion."""

    model = getattr(issue, "resolved_model", "")
    if not model:
        raise AgentRunnerError("Claude dispatch requires issue.resolved_model")

    started = clock()
    nonce = (nonce_factory or (lambda: uuid.uuid4().hex[:12]))()
    binding_name = _issue_binding_name(config, issue)
    if persist:
        socket_path = persistent_socket_path(binding_name, issue.id)
        namespace = socket_path.stem
        temp_dir = Path(mkdtemp(prefix=f"{namespace}-{nonce}-"))
    else:
        namespace = f"symphony-claude-{issue.id}-{nonce}"
        temp_dir = Path(mkdtemp(prefix=f"{namespace}-"))
        socket_path = Path("/tmp") / f"{namespace}.sock"
    session_name = namespace
    prompt_file = temp_dir / "prompt.txt"
    result_file = temp_dir / "result.0.txt"
    done_file = temp_dir / "done.0"
    cleanup = ClaudeRunCleanup(
        socket_path, session_name, temp_dir, run_func, remove_tree
    )
    session_reusable = False
    run_id = str(getattr(issue, "active_run_id", "") or "")
    source_env = dict(os.environ) if environ is None else environ

    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        cwd = _resolve_cwd(config, issue, create_worktree_func=create_worktree_func)
        env = _claude_env(issue, source_env)
        session_id = getattr(issue, "agent_session_id", "") or derive_session_id(
            issue.id
        )
        resume_requested = bool(getattr(issue, "resumed", False))
        transcript_file = session_file or session_file_path("claude", cwd, session_id)
        metadata_dir = pidfile_dir or _claude_pidfile_dir(source_env)
        metadata_path = metadata_dir / f"{socket_path.stem}.meta.json"
        pidfile_path = metadata_dir / f"{socket_path.stem}.pid"
        # `claude --session-id <id>` creates a fresh session and aborts when a
        # transcript for that id already exists; `--resume <id>` attaches to it.
        # The per-issue session id is deterministic, so a refeed (resumed=false,
        # e.g. after sha-drift) targets the same transcript an earlier successful
        # run wrote. Forcing --session-id there collides and claude exits before
        # readiness, surfacing as claude_ready_timeout. Pick the flag by
        # transcript existence; the resumed flag governs prompt *content*
        # (incremental vs full re-feed) upstream, not this launch flag.
        session_arg = (
            "--resume"
            if (resume_requested or transcript_file.exists())
            else "--session-id"
        )
        LOGGER.info(
            "claude_dispatch issue_id=%s model=%s cwd=%s session_id=%s resumed=%s",
            issue.id,
            model,
            cwd,
            session_id,
            str(resume_requested).lower(),
        )
        prompt_file.write_text(
            _wrap_prompt(rendered_prompt, result_file, done_file, issue),
            encoding="utf-8",
        )
        reattached = False
        if persist and _persistent_session_live(
            socket_path, session_name, run_func=run_func
        ):
            cleanup.metadata_path = _write_claude_session_metadata(
                metadata_path,
                issue_id=issue.id,
                binding=binding_name,
                cwd=cwd,
                session_file=transcript_file,
                session_name=session_name,
            )
            cleanup.pidfile_path = _register_claude_run(
                socket_path,
                session_name,
                run_func=run_func,
                pidfile_dir=metadata_dir,
            )
            reattached = _paste_and_submit(
                run_func, socket_path, session_name, prompt_file, sleep=sleep
            )
            if reattached:
                LOGGER.info(
                    "claude_reattached issue_id=%s socket=%s", issue.id, socket_path
                )
            else:
                _cleanup_claude_session_artifacts(
                    socket_path,
                    session_name,
                    run_func=run_func,
                    pidfile_path=cleanup.pidfile_path,
                    metadata_path=cleanup.metadata_path,
                )
                cleanup.pidfile_path = None
                cleanup.metadata_path = None

        if not reattached:
            if persist and socket_path.exists():
                _cleanup_claude_session_artifacts(
                    socket_path,
                    session_name,
                    run_func=run_func,
                    pidfile_path=pidfile_path,
                    metadata_path=metadata_path,
                )
            cleanup.metadata_path = _write_claude_session_metadata(
                metadata_path,
                issue_id=issue.id,
                binding=binding_name,
                cwd=cwd,
                session_file=transcript_file,
                session_name=session_name,
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
                stderr = strip_ansi(f"{launch.stdout}\n{launch.stderr}".strip())
                return _logged_result(issue, 1, duration_ms, False, "", stderr)

            cleanup.pidfile_path = _register_claude_run(
                socket_path,
                session_name,
                run_func=run_func,
                pidfile_dir=metadata_dir,
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

            _paste_and_submit(
                run_func, socket_path, session_name, prompt_file, sleep=sleep
            )

        deadline = started + (config.run_timeout_ms / 1000)
        poll_result = _poll_claude_until_done(
            issue,
            started,
            deadline,
            done_file,
            result_file,
            socket_path,
            session_name,
            transcript_file,
            prompt_file,
            run_id=run_id,
            source_env=source_env,
            clock=clock,
            sleep=sleep,
            run_func=run_func,
        )
        if poll_result is not None:
            if persist and poll_result.exit_code == 0 and not poll_result.timed_out:
                session_reusable = True
            return poll_result
        raise RuntimeError("_poll_claude_until_done returned None unexpectedly")
    finally:
        if run_id:
            with suppress(Exception):
                import_module("web.api.steer_queue").clear_steer_queue(
                    run_id, environ=source_env
                )
        cleanup.cleanup_run()
        if not (persist and session_reusable):
            cleanup.cleanup_session()


def _poll_claude_until_done(
    issue: CandidateIssue,
    started: float,
    deadline: float,
    done_file: Path,
    result_file: Path,
    socket_path: Path,
    session_name: str,
    transcript_file: Path,
    prompt_file: Path,
    *,
    run_id: str,
    source_env: Mapping[str, str],
    clock: Callable[[], float],
    sleep: Callable[[float], object],
    run_func: Callable[..., CompletedLike],
) -> AgentResult | None:
    """Poll tmux Claude session until done file, session death, idle, or timeout.

    Returns an ``AgentResult`` when the poll terminates. The return type
    includes ``None`` for future expansion; currently all paths return a result.
    """
    last_pane: str | None = None
    last_mtime: float | None = None
    unchanged_polls = 0
    nudges_used = 0
    modals_dismissed = 0
    generation = 0
    steer_offset = 0
    read_queued_steers = _load_steer_reader(run_id)
    active_result = result_file
    active_done = done_file

    while clock() <= deadline:
        if active_done.exists():
            records, steer_offset = _read_steer_records(
                run_id,
                steer_offset,
                read_queued_steers=read_queued_steers,
                source_env=source_env,
            )
            generation, active_result, active_done, delivered = _deliver_steer_records(
                issue,
                records,
                generation,
                prompt_file,
                socket_path,
                session_name,
                run_func=run_func,
                sleep=sleep,
            )
            if delivered:
                unchanged_polls = 0
                nudges_used = 0
                last_pane = None
                last_mtime = None
                continue

            stdout = _read_result_with_grace(active_result, sleep=sleep)
            if not stdout.strip():
                duration_ms = int((clock() - started) * 1000)
                pane = _capture_pane_tail(socket_path, session_name, run_func=run_func)
                stderr = (
                    "claude done file exists but result file is missing or "
                    f"empty after {RESULT_GRACE_SECONDS:g}s grace\n{pane}"
                )
                return _logged_result(issue, 137, duration_ms, False, "", stderr)
            stderr = _capture_pane_full(socket_path, session_name, run_func=run_func)
            duration_ms = int((clock() - started) * 1000)
            return _logged_result(issue, 0, duration_ms, False, stdout, stderr)

        records, steer_offset = _read_steer_records(
            run_id,
            steer_offset,
            read_queued_steers=read_queued_steers,
            source_env=source_env,
        )
        generation, active_result, active_done, delivered = _deliver_steer_records(
            issue,
            records,
            generation,
            prompt_file,
            socket_path,
            session_name,
            run_func=run_func,
            sleep=sleep,
        )
        if delivered:
            unchanged_polls = 0
            nudges_used = 0
            last_pane = None
            last_mtime = None
            continue

        if not _session_alive(socket_path, session_name, run_func=run_func):
            duration_ms = int((clock() - started) * 1000)
            stderr = _capture_pane_tail(socket_path, session_name, run_func=run_func)
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
            if _hit_permission_modal(pane):
                _send_escape(run_func, socket_path, session_name)
                modals_dismissed += 1
                LOGGER.info(
                    "claude_permission_modal_dismissed issue_id=%s dismiss=%s",
                    issue.id,
                    modals_dismissed,
                )
                if modals_dismissed >= MODAL_DISMISS_ATTEMPTS:
                    duration_ms = int((clock() - started) * 1000)
                    tail = _capture_pane_tail(
                        socket_path, session_name, run_func=run_func
                    )
                    stderr = (
                        "claude parked at a permission prompt that "
                        "--permission-mode bypassPermissions does not suppress "
                        "(e.g. an edit under .claude/); sent Escape to reject it "
                        f"{MODAL_DISMISS_ATTEMPTS} times but it kept reappearing, "
                        f"so the run was aborted\n{tail}"
                    )
                    LOGGER.info(
                        "claude_permission_modal_blocked issue_id=%s dismissed=%s "
                        "duration_ms=%s",
                        issue.id,
                        modals_dismissed,
                        duration_ms,
                    )
                    return _logged_result(issue, -1, duration_ms, False, "", stderr)
                unchanged_polls = 0
                last_pane = None
                last_mtime = None
                sleep(1.0)
                continue
            if nudges_used >= IDLE_NUDGE_ATTEMPTS:
                duration_ms = int((clock() - started) * 1000)
                tail = _capture_pane_tail(socket_path, session_name, run_func=run_func)
                stderr = (
                    "claude idle at prompt with no done file after "
                    f"{IDLE_NUDGE_ATTEMPTS} completion nudges; agent ended its "
                    "turn without completing the Symphony completion "
                    f"protocol\n{tail}"
                )
                LOGGER.info(
                    "claude_idle_no_completion issue_id=%s nudges=%s duration_ms=%s",
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
                active_result,
                active_done,
                sleep=sleep,
            )
            nudges_used += 1
            unchanged_polls = 0
            last_pane = None
            last_mtime = None
            LOGGER.info("claude_idle_nudge issue_id=%s nudge=%s", issue.id, nudges_used)
        sleep(1.0)

    duration_ms = int((clock() - started) * 1000)
    stderr = _capture_pane_tail(socket_path, session_name, run_func=run_func)
    return _logged_result(issue, -1, duration_ms, True, "", stderr)


def _load_steer_reader(
    run_id: str,
) -> Callable[..., tuple[list[Mapping[str, object]], int]] | None:
    """Load the transient steer queue reader only for runs that can steer."""

    if not run_id:
        return None
    try:
        return import_module("web.api.steer_queue").read_steer_records
    except Exception as exc:
        LOGGER.warning("claude_steer_queue_unavailable run_id=%s error=%s", run_id, exc)
        return None


def _read_steer_records(
    run_id: str,
    offset: int,
    *,
    read_queued_steers: Callable[..., tuple[list[Mapping[str, object]], int]] | None,
    source_env: Mapping[str, str],
) -> tuple[list[Mapping[str, object]], int]:
    if read_queued_steers is None:
        return [], offset
    try:
        return read_queued_steers(run_id, offset, environ=source_env)
    except Exception as exc:
        LOGGER.warning("claude_steer_read_failed run_id=%s error=%s", run_id, exc)
        return [], offset


def _deliver_steer_records(
    issue: CandidateIssue,
    records: Iterable[Mapping[str, object]],
    generation: int,
    prompt_file: Path,
    socket_path: Path,
    session_name: str,
    *,
    run_func: Callable[..., CompletedLike],
    sleep: Callable[[float], object],
) -> tuple[int, Path, Path, bool]:
    """Deliver queued Claude steer/abort records and return current gen paths."""

    active_result = _generation_result_path(prompt_file.parent, generation)
    active_done = _generation_done_path(prompt_file.parent, generation)
    delivered = False
    for record in records:
        kind = str(record.get("kind") or "")
        message = str(record.get("message") or "").strip()
        if kind == "abort":
            with suppress(OSError):
                _tmux(run_func, socket_path, "send-keys", "-t", session_name, "Escape")
        elif kind == "steer":
            if not message:
                continue
        else:
            continue

        generation += 1
        active_result = _generation_result_path(prompt_file.parent, generation)
        active_done = _generation_done_path(prompt_file.parent, generation)
        prompt_file.write_text(
            _steer_turn_text(kind, message, active_result, active_done),
            encoding="utf-8",
        )
        _paste_and_submit(run_func, socket_path, session_name, prompt_file, sleep=sleep)
        delivered = True
        LOGGER.info(
            "claude_steer_delivered issue_id=%s kind=%s generation=%s",
            issue.id,
            kind,
            generation,
        )
    return generation, active_result, active_done, delivered


def _generation_result_path(temp_dir: Path, generation: int) -> Path:
    return temp_dir / f"result.{generation}.txt"


def _generation_done_path(temp_dir: Path, generation: int) -> Path:
    return temp_dir / f"done.{generation}"


def _steer_turn_text(
    kind: str, message: str, result_file: Path, done_file: Path
) -> str:
    if kind == "abort":
        intro = (
            "Operator requested abort for the current Claude turn. Stop the "
            "current turn safely, then continue from this operator instruction."
        )
    else:
        intro = f"Operator steer for the current Claude run:\n\n{message}"
    return f"{intro}\n\n{_completion_protocol_text(result_file, done_file)}"


def _resolve_cwd(
    config: SymphonyConfig,
    issue: CandidateIssue,
    *,
    create_worktree_func: Callable[[Path, str, str, str], Path] | None,
) -> Path:
    if getattr(issue, "worktree_active", False):
        worktree_factory = create_worktree_func
        if worktree_factory is None:
            worktree_factory = import_module("worktree_facade").create_worktree
        binding_name = getattr(issue, "binding_name", "") or (
            config.bindings[0].name if config.bindings else ""
        )
        base_branch = getattr(issue, "base_branch", "") or config.base_branch or "main"
        return worktree_factory(
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
    return f"""You are running unattended for Symphony. Nobody can respond live. Do not use the ask_user_question tool. Do not use any other interactive tools that require the user.
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
    return strip_ansi(result.stdout or result.stderr or "")


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
    return strip_ansi(result.stdout or result.stderr or "")


def _paste_and_submit(
    run_func: Callable[..., CompletedLike],
    socket_path: Path,
    session_name: str,
    prompt_file: Path,
    *,
    sleep: Callable[[float], object],
) -> bool:
    """Paste the prompt and submit it, tolerating the tmux paste/Enter race.

    Settle after paste-buffer before the first Enter, then re-send Enter while
    the pane still shows the unsubmitted `[Pasted text …]` placeholder (up to
    ``SUBMIT_RETRY_ATTEMPTS``). Once the placeholder clears, the prompt was
    submitted; a stray Enter on the already-submitted prompt is harmless.
    """
    try:
        load = _tmux(run_func, socket_path, "load-buffer", str(prompt_file))
        if int(load.returncode) != 0:
            return False
        paste = _tmux(run_func, socket_path, "paste-buffer", "-t", session_name)
        if int(paste.returncode) != 0:
            return False
        sleep(PASTE_SETTLE_SECONDS)
        for _ in range(SUBMIT_RETRY_ATTEMPTS):
            submit = _tmux(
                run_func, socket_path, "send-keys", "-t", session_name, "Enter"
            )
            if int(submit.returncode) != 0:
                return False
            sleep(SUBMIT_RETRY_INTERVAL_SECONDS)
            capture = _tmux(run_func, socket_path, "capture-pane", "-pt", session_name)
            if int(capture.returncode) != 0:
                return False
            pane = strip_ansi(capture.stdout or capture.stderr or "")
            if not _paste_pending(pane):
                return True
    except OSError:
        return False
    return False


def _paste_pending(pane: str) -> bool:
    """True when the pane still shows an unsubmitted pasted-prompt placeholder."""
    return "pasted text" in pane.lower()


def _completion_protocol_text(result_file: Path, done_file: Path) -> str:
    """Completion-protocol reminder for a specific generation's files."""

    return (
        "Finish now, in order:\n"
        "1. Use your Write tool to write your full final output (the "
        "SYMPHONY_RESULT line plus the SYMPHONY_SUMMARY_BEGIN/SYMPHONY_SUMMARY_END "
        "block, or a SYMPHONY_QUESTION_BEGIN/SYMPHONY_QUESTION_END block) to this "
        f"literal result file path: {result_file}\n"
        f"2. Confirm the result file exists and is non-empty (test -s {result_file}).\n"
        f"3. ONLY after that confirmation, create this literal done file path: "
        f"{done_file}\n"
        "Do NOT create the done file if the result file is missing or empty."
    )


def _nudge_text(result_file: Path, done_file: Path) -> str:
    """Reminder pasted into an idle session to finish the completion protocol."""
    return (
        "You appear to have stopped without completing the Symphony completion "
        "protocol. Nobody can respond live. "
        f"{_completion_protocol_text(result_file, done_file)}"
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


def _hit_permission_modal(pane: str) -> bool:
    """True when the pane is parked on a Claude permission-confirmation modal.

    Requires both a numbered Yes/No choice line and a modal hint footer so a
    static pane of ordinary agent output never trips the detector.
    """
    return bool(_MODAL_CHOICE_RE.search(pane) and _MODAL_HINT_RE.search(pane))


def _send_escape(
    run_func: Callable[..., CompletedLike],
    socket_path: Path,
    session_name: str,
) -> None:
    """Send Escape to reject a Claude permission modal (mirrors the abort path)."""
    with suppress(OSError):
        _tmux(run_func, socket_path, "send-keys", "-t", session_name, "Escape")


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
