"""Launch Claude agents through an interactive tmux session."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from agent_runner import AgentResult, AgentRunnerError, CompletedLike, _strip_ansi
from config import SymphonyConfig
from plane_poller import CandidateIssue


LOGGER = logging.getLogger(__name__)
READY_TIMEOUT_SECONDS = 30.0
READY_PATTERN = "bypass permissions on|shift+tab to cycle"


@dataclass
class ClaudeRunCleanup:
    """Idempotent cleanup for per-run tmux and filesystem artifacts."""

    socket_path: Path
    session_name: str
    temp_dir: Path
    run_func: Callable[..., CompletedLike] = subprocess.run
    remove_tree: Callable[[str], object] = shutil.rmtree
    cleaned: bool = field(default=False, init=False)

    def cleanup(self) -> None:
        if self.cleaned:
            return
        self.cleaned = True
        with suppress(OSError):
            self.run_func(
                ["tmux", "-S", str(self.socket_path), "kill-session", "-t", self.session_name],
                capture_output=True,
                text=True,
                check=False,
            )
        with suppress(OSError):
            self.socket_path.unlink(missing_ok=True)
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
    cleanup = ClaudeRunCleanup(socket_path, session_name, temp_dir, run_func, remove_tree)

    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        cwd = _resolve_cwd(config, issue, create_worktree_func=create_worktree_func)
        source_env = dict(os.environ) if environ is None else environ
        env = _claude_env(issue, source_env)
        LOGGER.info(
            "claude_dispatch issue_id=%s model=%s cwd=%s",
            issue.id,
            model,
            cwd,
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
        _tmux(run_func, socket_path, "load-buffer", str(prompt_file))
        _tmux(run_func, socket_path, "paste-buffer", "-t", session_name)
        _tmux(run_func, socket_path, "send-keys", "-t", session_name, "Enter")

        deadline = started + (config.run_timeout_ms / 1000)
        while clock() <= deadline:
            if done_file.exists():
                if not result_file.exists() or not result_file.read_text(encoding="utf-8").strip():
                    duration_ms = int((clock() - started) * 1000)
                    stderr = "claude done file exists but result file is missing or empty"
                    return _logged_result(issue, 137, duration_ms, False, "", stderr)
                stdout = result_file.read_text(encoding="utf-8")
                stderr = _capture_pane_full(socket_path, session_name, run_func=run_func)
                duration_ms = int((clock() - started) * 1000)
                return _logged_result(issue, 0, duration_ms, False, stdout, stderr)
            if not _session_alive(socket_path, session_name, run_func=run_func):
                duration_ms = int((clock() - started) * 1000)
                stderr = _capture_pane_tail(socket_path, session_name, run_func=run_func)
                return _logged_result(issue, 1, duration_ms, False, "", stderr)
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
        return create_worktree_func(config.homelab_repo_path, binding_name, issue.id, base_branch)
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
    skill_directive = f"\nInvoke the `{skill}` skill by name before doing the work." if skill else ""
    return f"""You are running unattended for Symphony. Nobody can respond to questions.
Never ask questions. Never end your turn awaiting operator input. If genuinely blocked, write `SYMPHONY_RESULT: blocked` and still touch the done file.{skill_directive}

Write your full final output, including exactly one `SYMPHONY_RESULT: done|review|blocked` line and optional `SYMPHONY_SUMMARY:` line, to this literal result file path using Bash:
{result_file}
Write the result file FIRST. Then touch this literal done file path:
{done_file}

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


def _tmux(run_func: Callable[..., CompletedLike], socket_path: Path, *args: str) -> CompletedLike:
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
        result = _tmux(run_func, socket_path, "capture-pane", "-pt", session_name, "-S", "-200")
    except OSError:
        return ""
    return _strip_ansi(result.stdout or result.stderr or "")


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
