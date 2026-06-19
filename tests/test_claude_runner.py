from __future__ import annotations

import importlib
import logging
import subprocess
from itertools import chain, repeat
from pathlib import Path

import pytest

from agent_runner import AgentRunnerError
from config import SymphonyConfig
from plane_poller import CandidateIssue

claude_runner = importlib.import_module("claude_runner")
ClaudeRunCleanup = claude_runner.ClaudeRunCleanup
claude_probe_failure_reason = claude_runner.claude_probe_failure_reason
reap_orphan_claude_sockets = claude_runner.reap_orphan_claude_sockets
run_claude_agent = claude_runner.run_claude_agent
set_claude_probe_failure_reason = claude_runner.set_claude_probe_failure_reason
verify_claude_support = claude_runner.verify_claude_support


class Completed:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _config(tmp_path: Path, *, timeout_ms: int = 1000) -> SymphonyConfig:
    return SymphonyConfig(
        plane_api_url="https://plane.example.test",
        plane_api_key="fake-plane-key-for-tests",
        plane_workspace_slug="homelab",
        plane_project_id="fake-project-id",
        homelab_repo_path=tmp_path,
        pi_bin="pi",
        run_timeout_ms=timeout_ms,
    )


def _issue(**kwargs) -> CandidateIssue:
    values = {
        "id": "42",
        "identifier": "HOM-42",
        "name": "Claude issue",
        "description": "Test description",
        "labels": (),
        "created_at": "2026-06-13T00:00:00+00:00",
        "resolved_model": "claude-opus-4-8",
    }
    values.update(kwargs)
    return CandidateIssue(**values)


@pytest.fixture(autouse=True)
def reset_claude_probe_state():
    set_claude_probe_failure_reason(None)
    yield
    set_claude_probe_failure_reason(None)


class TmuxFake:
    def __init__(self, *, pane: str = "bypass permissions on", result_text: str = ""):
        self.calls: list[tuple[list[str], dict]] = []
        self.pane = pane
        self.result_text = result_text
        self.prompt_path: Path | None = None
        self.result_file: Path | None = None
        self.done_file: Path | None = None

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if command[:1] != ["tmux"]:
            return Completed()
        if "new-session" in command:
            return Completed()
        if "capture-pane" in command:
            return Completed(stdout=self.pane)
        if "load-buffer" in command:
            self.prompt_path = Path(command[-1])
            prompt = self.prompt_path.read_text(encoding="utf-8")
            self.result_file = _path_after(prompt, "literal result file path:")
            self.done_file = _path_after(prompt, "literal done file path:")
            return Completed()
        if "send-keys" in command and self.result_text is not None:
            assert self.result_file is not None
            assert self.done_file is not None
            self.result_file.write_text(self.result_text, encoding="utf-8")
            self.done_file.write_text("", encoding="utf-8")
            return Completed()
        if "has-session" in command:
            return Completed(returncode=0)
        return Completed()


def _path_after(text: str, marker: str) -> Path:
    return Path(text.split(marker, 1)[1].strip().splitlines()[0])


def test_verify_claude_support_success_clears_probe_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    set_claude_probe_failure_reason("old failure")

    verify_claude_support(
        run_func=lambda *args, **kwargs: Completed(stdout="Claude Code 1.0"),
        which_func=lambda binary, path=None: f"/usr/bin/{binary}",
        environ={"PATH": "/usr/bin"},
    )

    assert claude_probe_failure_reason() is None
    assert "claude_probe_ok" in caplog.text


@pytest.mark.parametrize(
    ("run_func", "expected"),
    [
        (
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("missing")),
            "could not run: missing",
        ),
        (
            lambda *args, **kwargs: Completed(stderr="bad auth", returncode=2),
            "failed with exit code 2: bad auth",
        ),
        (
            lambda *args, **kwargs: (_ for _ in ()).throw(
                subprocess.TimeoutExpired(["claude", "--version"], 3)
            ),
            "timed out after 3s",
        ),
    ],
)
def test_verify_claude_support_failure_records_reason_and_does_not_raise(
    caplog: pytest.LogCaptureFixture,
    run_func,
    expected: str,
) -> None:
    caplog.set_level(logging.WARNING)

    verify_claude_support(
        run_func=run_func,
        which_func=lambda binary, path=None: f"/usr/bin/{binary}",
        environ={"PATH": "/usr/bin"},
        timeout=3,
    )

    assert expected in (claude_probe_failure_reason() or "")
    assert "claude_probe_failed reason=" in caplog.text


def test_verify_claude_support_missing_binary_records_reason() -> None:
    verify_claude_support(
        run_func=lambda *args, **kwargs: Completed(),
        which_func=lambda binary, path=None: (
            None if binary == "claude" else f"/usr/bin/{binary}"
        ),
        environ={"PATH": "/usr/bin"},
    )

    assert claude_probe_failure_reason() == "claude binary not found on PATH"


def test_reap_orphan_claude_sockets_kills_removes_and_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    sockets = [
        tmp_path / "symphony-claude-1-a.sock",
        tmp_path / "symphony-claude-2-b.sock",
    ]
    calls: list[list[str]] = []
    removed: list[Path] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            return Completed(returncode=1)
        return Completed()

    count = reap_orphan_claude_sockets(
        glob_func=lambda pattern: sockets,
        run_func=fake_run,
        unlink_func=lambda path: removed.append(path),
        pidfile_dir=tmp_path / "claude",
    )

    assert count == 2
    assert calls == [
        ["tmux", "-S", str(sockets[0]), "kill-server"],
        ["tmux", "-S", str(sockets[1]), "kill-server"],
    ]
    assert removed == sockets
    assert f"claude_socket_reaped path={sockets[0]}" in caplog.text
    assert "claude_socket_reap_done count=2" in caplog.text


def test_reap_orphan_claude_sockets_no_sockets_skips_tmux(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    count = reap_orphan_claude_sockets(
        glob_func=lambda pattern: [],
        run_func=lambda command, **kwargs: calls.append(command) or Completed(),
        pidfile_dir=tmp_path / "claude",
    )

    assert count == 0
    assert calls == []


@pytest.mark.parametrize("lock_confirmed", [False, True])
def test_reap_orphan_claude_sockets_skips_live_owned_non_persistent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, lock_confirmed: bool
) -> None:
    """A nonce socket whose sidecar pidfile names a still-live, matching tmux server is
    a live run and must never be killed, even outside the boot sweep."""
    caplog.set_level(logging.INFO)
    pid_dir = tmp_path / "claude"
    pid_dir.mkdir()
    socket = tmp_path / "symphony-claude-1-a.sock"
    (pid_dir / "symphony-claude-1-a.pid").write_text("999 12345", encoding="utf-8")
    calls: list[list[str]] = []
    removed: list[Path] = []

    count = reap_orphan_claude_sockets(
        lock_confirmed=lock_confirmed,
        glob_func=lambda pattern: [socket],
        run_func=lambda command, **kwargs: calls.append(command) or Completed(),
        unlink_func=lambda path: removed.append(path),
        pidfile_dir=pid_dir,
        is_alive=lambda pid: pid == 999,
        read_start_time=lambda pid: "12345",
    )

    assert count == 0
    assert calls == []
    assert removed == []
    assert f"claude_socket_skipped_live path={socket}" in caplog.text


def test_reap_orphan_claude_sockets_keeps_live_persistent_without_lock(
    tmp_path: Path,
) -> None:
    pid_dir = tmp_path / "claude"
    pid_dir.mkdir()
    socket = tmp_path / "symphony-claude-persist-homelab-42.sock"
    socket.write_text("", encoding="utf-8")
    pidfile = pid_dir / "symphony-claude-persist-homelab-42.pid"
    pidfile.write_text("999 12345", encoding="utf-8")
    calls: list[list[str]] = []
    removed: list[Path] = []

    count = reap_orphan_claude_sockets(
        lock_confirmed=False,
        glob_func=lambda pattern: [socket],
        run_func=lambda command, **kwargs: calls.append(command) or Completed(),
        unlink_func=lambda path: removed.append(path),
        pidfile_dir=pid_dir,
        is_alive=lambda pid: pid == 999,
        read_start_time=lambda pid: "12345",
    )

    assert count == 0
    assert calls == []
    assert removed == []


def test_reap_orphan_claude_sockets_reaps_live_persistent_with_lock(
    tmp_path: Path,
) -> None:
    pid_dir = tmp_path / "claude"
    pid_dir.mkdir()
    socket = tmp_path / "symphony-claude-persist-homelab-42.sock"
    socket.write_text("", encoding="utf-8")
    pidfile = pid_dir / "symphony-claude-persist-homelab-42.pid"
    pidfile.write_text("999 12345", encoding="utf-8")
    calls: list[list[str]] = []
    removed: list[Path] = []

    def unlink(path: Path) -> None:
        removed.append(path)
        path.unlink(missing_ok=True)

    count = reap_orphan_claude_sockets(
        lock_confirmed=True,
        glob_func=lambda pattern: [socket],
        run_func=lambda command, **kwargs: calls.append(command) or Completed(),
        unlink_func=unlink,
        pidfile_dir=pid_dir,
        is_alive=lambda pid: pid == 999,
        read_start_time=lambda pid: "12345",
    )

    assert count == 1
    assert calls == [["tmux", "-S", str(socket), "kill-server"]]
    assert removed == [socket, pidfile]


def test_reap_orphan_claude_sockets_reaps_dead_owner(tmp_path: Path) -> None:
    """A socket whose recorded tmux server pid is dead is a true orphan: the
    stale socket and its sidecar pidfile are reaped."""
    pid_dir = tmp_path / "claude"
    pid_dir.mkdir()
    socket = tmp_path / "symphony-claude-1-a.sock"
    pidfile = pid_dir / "symphony-claude-1-a.pid"
    pidfile.write_text("999 12345", encoding="utf-8")
    calls: list[list[str]] = []
    removed: list[Path] = []

    count = reap_orphan_claude_sockets(
        glob_func=lambda pattern: [socket],
        run_func=lambda command, **kwargs: calls.append(command) or Completed(),
        unlink_func=lambda path: removed.append(path),
        pidfile_dir=pid_dir,
        is_alive=lambda pid: False,
        read_start_time=lambda pid: "12345",
    )

    assert count == 1
    assert calls == [["tmux", "-S", str(socket), "kill-server"]]
    assert removed == [socket, pidfile]


def test_reap_orphan_claude_sockets_reaps_on_start_time_mismatch(
    tmp_path: Path,
) -> None:
    """An alive pid whose start-time no longer matches the recorded value (pid
    reuse) is not the original tmux server, so the stale socket is reaped."""
    pid_dir = tmp_path / "claude"
    pid_dir.mkdir()
    socket = tmp_path / "symphony-claude-1-a.sock"
    pidfile = pid_dir / "symphony-claude-1-a.pid"
    pidfile.write_text("999 12345", encoding="utf-8")
    calls: list[list[str]] = []
    removed: list[Path] = []

    count = reap_orphan_claude_sockets(
        glob_func=lambda pattern: [socket],
        run_func=lambda command, **kwargs: calls.append(command) or Completed(),
        unlink_func=lambda path: removed.append(path),
        pidfile_dir=pid_dir,
        is_alive=lambda pid: True,
        read_start_time=lambda pid: "99999",
    )

    assert count == 1
    assert calls == [["tmux", "-S", str(socket), "kill-server"]]
    assert removed == [socket, pidfile]


def test_reap_orphan_claude_sockets_sweeps_leaked_sidecar(tmp_path: Path) -> None:
    """A sidecar whose tmux server crashed (its socket already gone, so absent
    from the glob) is still swept when its recorded pid is dead; a live one is
    kept. Prevents sidecar leak across boots off a PrivateTmp mount."""
    pid_dir = tmp_path / "claude"
    pid_dir.mkdir()
    live = pid_dir / "symphony-claude-8-y.pid"
    live.write_text("999 67890", encoding="utf-8")
    leaked = pid_dir / "symphony-claude-9-z.pid"
    leaked.write_text("404 12345", encoding="utf-8")
    removed: list[Path] = []

    count = reap_orphan_claude_sockets(
        glob_func=lambda pattern: [],
        run_func=lambda command, **kwargs: Completed(),
        unlink_func=lambda path: removed.append(path),
        pidfile_dir=pid_dir,
        is_alive=lambda pid: pid == 999,
        read_start_time=lambda pid: "67890" if pid == 999 else "12345",
    )

    assert count == 0
    assert removed == [leaked]


def test_register_claude_run_writes_server_pid_and_start_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_dir = tmp_path / "claude"
    monkeypatch.setattr(claude_runner, "pid_start_time", lambda pid: "778899")

    def fake_run(command, **kwargs):
        assert "display-message" in command
        return Completed(stdout="4242\n")

    pidfile = claude_runner._register_claude_run(
        Path("/tmp/symphony-claude-1-a.sock"),
        "symphony-claude-1-a",
        run_func=fake_run,
        pidfile_dir=pid_dir,
    )

    assert pidfile == pid_dir / "symphony-claude-1-a.pid"
    assert pidfile.read_text(encoding="utf-8") == "4242 778899"


def test_register_claude_run_skips_when_server_pid_unavailable(
    tmp_path: Path,
) -> None:
    pid_dir = tmp_path / "claude"

    pidfile = claude_runner._register_claude_run(
        Path("/tmp/symphony-claude-1-a.sock"),
        "symphony-claude-1-a",
        run_func=lambda command, **kwargs: Completed(stdout=""),
        pidfile_dir=pid_dir,
    )

    assert pidfile is None
    assert not pid_dir.exists()


def test_claude_cleanup_removes_pidfile(tmp_path: Path) -> None:
    pidfile = tmp_path / "symphony-claude-1-a.pid"
    pidfile.write_text("4242 778899", encoding="utf-8")

    cleanup = ClaudeRunCleanup(
        tmp_path / "missing.sock",
        "missing-session",
        tmp_path / "missing-dir",
        run_func=lambda *a, **k: Completed(),
        pidfile_path=pidfile,
    )
    cleanup.cleanup()

    assert not pidfile.exists()


def test_claude_success_uses_result_file_stdout_and_pane_stderr(tmp_path: Path) -> None:
    fake = TmuxFake(
        pane="\x1b[31mshift+tab to cycle\x1b[0m", result_text="hello without marker"
    )

    result = run_claude_agent(
        _config(tmp_path),
        _issue(),
        "rendered prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
    )

    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.stdout == "hello without marker"
    assert result.stderr == "shift+tab to cycle"


def test_claude_ready_timeout_is_fast_synthetic_failure(tmp_path: Path) -> None:
    fake = TmuxFake(pane="auth prompt")
    times = iter([0.0, 0.0, 1.0, 1.1])

    result = run_claude_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: next(times),
        sleep=lambda _: None,
        ready_timeout_s=0,
    )

    assert result.exit_code == 1
    assert result.timed_out is False
    assert result.stdout == ""
    assert result.stderr.startswith("claude_ready_timeout\nauth prompt")


def test_claude_session_dead_without_done_returns_pane_tail(tmp_path: Path) -> None:
    fake = TmuxFake(pane="shift+tab to cycle\ncrashed", result_text=None)  # type: ignore[arg-type]

    def fake_run(command, **kwargs):
        if "has-session" in command:
            fake.calls.append((command, kwargs))
            return Completed(returncode=1)
        return fake(command, **kwargs)

    result = run_claude_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        run_func=fake_run,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
    )

    assert result.exit_code == 1
    assert result.timed_out is False
    assert "crashed" in result.stderr


@pytest.mark.parametrize("result_text", ["", "   \n"])
def test_claude_done_with_missing_or_empty_result_is_loud(
    tmp_path: Path, result_text: str
) -> None:
    fake = TmuxFake(result_text=result_text)

    result = run_claude_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
    )

    assert result.exit_code == 137
    assert result.timed_out is False
    assert "result file is missing or empty" in result.stderr


class _SubmitRaceTmux:
    """Pane keeps the unsubmitted `[Pasted text …]` placeholder until the 2nd
    Enter, mimicking a large paste whose first Enter is absorbed."""

    def __init__(self, result_text: str = "SYMPHONY_RESULT: done"):
        self.calls: list[list[str]] = []
        self.enters = 0
        self.pasted = False
        self.result_file: Path | None = None
        self.done_file: Path | None = None
        self.result_text = result_text

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if "load-buffer" in command:
            prompt = Path(command[-1]).read_text(encoding="utf-8")
            self.result_file = _path_after(prompt, "literal result file path:")
            self.done_file = _path_after(prompt, "literal done file path:")
            return Completed()
        if "paste-buffer" in command:
            self.pasted = True
            return Completed()
        if "send-keys" in command:
            self.enters += 1
            if self.enters >= 2 and self.result_file and self.done_file:
                self.result_file.write_text(self.result_text, encoding="utf-8")
                self.done_file.write_text("", encoding="utf-8")
            return Completed()
        if "capture-pane" in command:
            if self.pasted and self.enters < 2:
                return Completed(stdout="❯ [Pasted text #1 +200 lines]")
            return Completed(stdout="bypass permissions on")
        if "has-session" in command:
            return Completed(returncode=0)
        return Completed()


def test_claude_resubmits_when_paste_not_yet_submitted(tmp_path: Path) -> None:
    fake = _SubmitRaceTmux()

    result = run_claude_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
    )

    enters = sum(1 for command in fake.calls if "send-keys" in command)
    assert enters == 2  # first Enter absorbed; re-sent once the placeholder cleared
    assert result.exit_code == 0


class _DoneNoResultTmux:
    """Touches the done file on Enter but never writes the result, so the result
    must fill during the grace window (driven by the test's sleep)."""

    def __init__(self, pane: str = "bypass permissions on"):
        self.pane = pane
        self.result_file: Path | None = None
        self.done_file: Path | None = None

    def __call__(self, command, **kwargs):
        if "load-buffer" in command:
            prompt = Path(command[-1]).read_text(encoding="utf-8")
            self.result_file = _path_after(prompt, "literal result file path:")
            self.done_file = _path_after(prompt, "literal done file path:")
            return Completed()
        if "send-keys" in command and self.done_file is not None:
            self.done_file.write_text("", encoding="utf-8")
            return Completed()
        if "capture-pane" in command:
            return Completed(stdout=self.pane)
        if "has-session" in command:
            return Completed(returncode=0)
        return Completed()


def test_claude_done_empty_result_fills_during_grace_succeeds(tmp_path: Path) -> None:
    fake = _DoneNoResultTmux()
    state = {"filled": False}

    def fake_sleep(secs):
        # Fill the result on the first grace-window poll (step-sized sleep),
        # decoupled from the paste/submit settle sleeps.
        if secs == claude_runner.RESULT_GRACE_STEP_SECONDS and not state["filled"]:
            state["filled"] = True
            assert fake.result_file is not None
            fake.result_file.write_text("SYMPHONY_RESULT: done\nbody", encoding="utf-8")

    result = run_claude_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=fake_sleep,
    )

    assert result.exit_code == 0
    assert "SYMPHONY_RESULT: done" in result.stdout


def test_claude_done_empty_failure_captures_pane(tmp_path: Path) -> None:
    fake = TmuxFake(pane="shift+tab to cycle\nclaude error MODEL_UNAVAILABLE")

    result = run_claude_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
    )

    assert result.exit_code == 137
    # Pane tail is captured into stderr for post-hoc diagnosis (was previously lost).
    assert "MODEL_UNAVAILABLE" in result.stderr


def test_claude_timeout_kills_session_and_marks_timed_out(tmp_path: Path) -> None:
    fake = TmuxFake(result_text=None)  # type: ignore[arg-type]
    times = chain([0.0, 0.0, 0.0, 0.0, 1.0], repeat(1.0))

    result = run_claude_agent(
        _config(tmp_path, timeout_ms=0),
        _issue(),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: next(times),
        sleep=lambda _: None,
    )

    assert result.exit_code == -1
    assert result.timed_out is True
    assert any("kill-session" in call[0] for call in fake.calls)


def test_claude_artifact_namespace_and_nonce_vary_per_run(tmp_path: Path) -> None:
    fakes: list[TmuxFake] = []

    for nonce in ["one", "two"]:
        fake = TmuxFake(result_text="SYMPHONY_RESULT: done")
        fakes.append(fake)
        run_claude_agent(
            _config(tmp_path),
            _issue(),
            "prompt",
            run_func=fake,
            mkdtemp=lambda prefix, n=nonce: str(tmp_path / f"{prefix}{n}"),
            remove_tree=lambda path: None,
            nonce_factory=lambda n=nonce: n,
            clock=lambda: 0.0,
            sleep=lambda _: None,
        )

    commands = [call[0] for fake in fakes for call in fake.calls]
    flattened = "\n".join(" ".join(command) for command in commands)
    assert "/tmp/symphony-claude-42-one.sock" in flattened
    assert "/tmp/symphony-claude-42-two.sock" in flattened
    assert "symphony-claude-42-one" in flattened
    assert "symphony-claude-42-two" in flattened


def test_claude_preamble_contains_paths_unattended_and_skill_directive(
    tmp_path: Path,
) -> None:
    fake = TmuxFake(result_text="SYMPHONY_RESULT: done")
    issue = _issue(preferred_skill="dev-build")

    run_claude_agent(
        _config(tmp_path),
        issue,
        "rendered prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
    )

    assert fake.prompt_path is not None
    prompt = fake.prompt_path.read_text(encoding="utf-8")
    assert "Nobody can respond live" in prompt
    assert "SYMPHONY_QUESTION_BEGIN" in prompt
    assert "Never ask questions" not in prompt
    assert str(fake.result_file) in prompt
    assert str(fake.done_file) in prompt
    assert "Invoke the `dev-build` skill by name" in prompt
    # Completion protocol (C-0174): robust Write-tool result write and
    # done-only-after-non-empty-result gating.
    assert "Write) tool" in prompt
    assert "NOT a shell heredoc" in prompt
    assert "Do NOT create it if the result file is missing or empty" in prompt


def test_claude_preamble_omits_skill_directive_when_absent(tmp_path: Path) -> None:
    fake = TmuxFake(result_text="SYMPHONY_RESULT: done")

    run_claude_agent(
        _config(tmp_path),
        _issue(preferred_skill=None),
        "rendered prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
    )

    assert fake.prompt_path is not None
    assert "Invoke the `" not in fake.prompt_path.read_text(encoding="utf-8")


def test_claude_env_allowlist_and_launch_argv_cwd(tmp_path: Path) -> None:
    fake = TmuxFake(result_text="SYMPHONY_RESULT: done")
    environ = {
        "PATH": "/usr/bin",
        "HOME": "/home/james",
        "USER": "james",
        "LANG": "C.UTF-8",
        "TMPDIR": "/tmp",
        "XDG_RUNTIME_DIR": "/run/user/1000",
        "TERM": "xterm",
        "NO_COLOR": "1",
        "PLANE_API_KEY": "secret",
    }

    run_claude_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
        environ=environ,
    )

    launch_call = next(call for call in fake.calls if "new-session" in call[0])
    command, kwargs = launch_call
    assert command[-7:] == [
        "claude",
        "--permission-mode",
        "bypassPermissions",
        "--model",
        "claude-opus-4-8",
        "--session-id",
        issue_session_id("42"),
    ]
    assert "-p" not in command
    assert "--continue" not in command
    assert "-c" not in command
    assert kwargs["cwd"] == str(tmp_path)
    env = kwargs["env"]
    assert sorted(env) == [
        "HOME",
        "LANG",
        "PATH",
        "SYMPHONY_ISSUE_ID",
        "TMPDIR",
        "USER",
        "XDG_RUNTIME_DIR",
    ]
    assert env["SYMPHONY_ISSUE_ID"] == "42"


def test_claude_worktree_active_uses_created_worktree_cwd(tmp_path: Path) -> None:
    fake = TmuxFake(result_text="SYMPHONY_RESULT: done")
    worktree = tmp_path / "worktree"

    def create_worktree(
        repo: Path, binding: str, issue_id: str, base_branch: str
    ) -> Path:
        assert repo == tmp_path
        assert binding == "homelab"
        assert issue_id == "42"
        assert base_branch == "main"
        return worktree

    run_claude_agent(
        _config(tmp_path),
        _issue(worktree_active=True, binding_name="homelab", base_branch="main"),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
        create_worktree_func=create_worktree,
    )

    launch_call = next(call for call in fake.calls if "new-session" in call[0])
    assert launch_call[1]["cwd"] == str(worktree)


def test_claude_cleanup_runs_on_exception_and_is_idempotent(tmp_path: Path) -> None:
    removed: list[str] = []
    calls: list[list[str]] = []

    def boom_after_launch(command, **kwargs):
        calls.append(command)
        if "capture-pane" in command:
            raise RuntimeError("boom")
        return Completed()

    with pytest.raises(RuntimeError, match="boom"):
        run_claude_agent(
            _config(tmp_path),
            _issue(),
            "prompt",
            run_func=boom_after_launch,
            mkdtemp=lambda **_: str(tmp_path / "run"),
            remove_tree=lambda path: removed.append(path),
            nonce_factory=lambda: "abc",
            clock=lambda: 0.0,
            sleep=lambda _: None,
        )

    assert any("kill-session" in command for command in calls)
    assert removed == [str(tmp_path / "run")]

    cleanup = ClaudeRunCleanup(
        tmp_path / "missing.sock",
        "missing-session",
        tmp_path / "missing-dir",
        run_func=lambda *a, **k: Completed(),
    )
    cleanup.cleanup()
    cleanup.cleanup()


def test_claude_empty_resolved_model_fails_before_tmux(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    with pytest.raises(AgentRunnerError, match="resolved_model"):
        run_claude_agent(
            _config(tmp_path),
            _issue(resolved_model=""),
            "prompt",
            run_func=lambda command, **kwargs: calls.append(command) or Completed(),
        )

    assert calls == []


def issue_session_id(issue_id: str) -> str:
    return claude_runner.derive_session_id(issue_id)


def test_claude_resume_launch_uses_resume_when_issue_is_resumed(tmp_path: Path) -> None:
    fake = TmuxFake(result_text="SYMPHONY_RESULT: done")
    session_id = issue_session_id("42")

    run_claude_agent(
        _config(tmp_path),
        _issue(agent_session_id=session_id, resumed=True),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
    )

    launch_call = next(call for call in fake.calls if "new-session" in call[0])
    command = launch_call[0]
    assert "--resume" in command
    assert command[command.index("--resume") + 1] == session_id
    assert "--session-id" not in command
    assert "--continue" not in command
    assert "-c" not in command


def test_claude_fresh_launch_uses_session_id_when_issue_is_not_resumed(
    tmp_path: Path,
) -> None:
    fake = TmuxFake(result_text="SYMPHONY_RESULT: done")
    session_id = issue_session_id("42")

    run_claude_agent(
        _config(tmp_path),
        _issue(agent_session_id=session_id, resumed=False),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
    )

    launch_call = next(call for call in fake.calls if "new-session" in call[0])
    command = launch_call[0]
    assert "--session-id" in command
    assert command[command.index("--session-id") + 1] == session_id
    assert "--resume" not in command
    assert "--continue" not in command
    assert "-c" not in command


def test_claude_refeed_uses_resume_when_transcript_already_exists(
    tmp_path: Path,
) -> None:
    # A sha-drift refeed arrives with resumed=False but the deterministic
    # session transcript from an earlier successful run is still on disk.
    # Launching with --session-id would collide and the agent would exit before
    # readiness; the runner must attach with --resume instead.
    fake = TmuxFake(result_text="SYMPHONY_RESULT: done")
    session_id = issue_session_id("42")
    transcript = tmp_path / f"{session_id}.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")

    run_claude_agent(
        _config(tmp_path),
        _issue(agent_session_id=session_id, resumed=False),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
        session_file=transcript,
    )

    launch_call = next(call for call in fake.calls if "new-session" in call[0])
    command = launch_call[0]
    assert "--resume" in command
    assert command[command.index("--resume") + 1] == session_id
    assert "--session-id" not in command


class _IdleThenNudgeCompletesTmux:
    """Static pane with no done file (agent parked at the prompt) until a
    completion nudge arrives, then writes the result + done file -- an agent that
    forgot the protocol and complies once reminded."""

    def __init__(
        self,
        pane: str = "bypass permissions on",
        result_text: str = "SYMPHONY_RESULT: done",
    ):
        self.calls: list[list[str]] = []
        self.pane = pane
        self.result_text = result_text
        self.result_file: Path | None = None
        self.done_file: Path | None = None
        self.nudged = False
        self.nudge_count = 0

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if "load-buffer" in command:
            prompt = Path(command[-1]).read_text(encoding="utf-8")
            self.result_file = _path_after(prompt, "literal result file path:")
            self.done_file = _path_after(prompt, "literal done file path:")
            if "appear to have stopped" in prompt:
                self.nudged = True
                self.nudge_count += 1
            return Completed()
        if "send-keys" in command:
            if self.nudged and self.result_file and self.done_file:
                self.result_file.write_text(self.result_text, encoding="utf-8")
                self.done_file.write_text("", encoding="utf-8")
            return Completed()
        if "capture-pane" in command:
            return Completed(stdout=self.pane)
        if "has-session" in command:
            return Completed(returncode=0)
        return Completed()


def test_claude_idle_without_done_is_nudged_then_completes(tmp_path: Path) -> None:
    fake = _IdleThenNudgeCompletesTmux()
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("", encoding="utf-8")  # static mtime => transcript idle

    result = run_claude_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
        session_file=transcript,
    )

    assert fake.nudge_count == 1  # parked agent reminded once, then finished
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.stdout == "SYMPHONY_RESULT: done"


class _IdleNeverCompletesTmux:
    """Static pane that never produces a done file even after nudges -- an agent
    that ended its turn and will not come back."""

    def __init__(self, pane: str = "bypass permissions on"):
        self.calls: list[list[str]] = []
        self.pane = pane
        self.nudge_count = 0

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if "load-buffer" in command:
            prompt = Path(command[-1]).read_text(encoding="utf-8")
            if "appear to have stopped" in prompt:
                self.nudge_count += 1
            return Completed()
        if "capture-pane" in command:
            return Completed(stdout=self.pane)
        if "has-session" in command:
            return Completed(returncode=0)
        return Completed()


def test_claude_idle_exhausts_nudges_and_fails_fast(tmp_path: Path) -> None:
    fake = _IdleNeverCompletesTmux()
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("", encoding="utf-8")  # static mtime => transcript idle

    result = run_claude_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,  # never trips run_timeout_ms; idle give-up terminates
        sleep=lambda _: None,
        session_file=transcript,
    )

    assert fake.nudge_count == claude_runner.IDLE_NUDGE_ATTEMPTS
    assert result.exit_code == -1
    assert result.timed_out is True
    assert "completion nudges" in result.stderr
    assert any("kill-session" in call for call in fake.calls)


_PERMISSION_MODAL = (
    "Do you want to make this edit to SKILL.md?\n"
    "❯ 1. Yes\n"
    "  2. Yes, and allow Claude to edit its own settings for this session\n"
    "  3. No\n\n"
    "Esc to cancel · Tab to amend\n\n"
    # Real Claude panes keep the status footer below the modal; include it so the
    # fixture passes _wait_until_ready (which matches this marker) instead of
    # spinning forever under a frozen clock.
    "⏵⏵ bypass permissions on (shift+tab to cycle)"
)


_QUESTION_MODAL = (
    "Which database should we use?\n"
    "❯ 1. Postgres\n"
    "  2. SQLite\n"
    "  3. MySQL\n\n"
    "↑/↓ to select · Esc to cancel\n\n"
    # Same status footer as the permission fixture, so _wait_until_ready passes.
    "⏵⏵ bypass permissions on (shift+tab to cycle)"
)


class _PermissionModalThenApprovesTmux:
    """Pane parked on a permission modal until Enter approves the pre-selected
    'Yes'; the agent then proceeds and finishes the completion protocol."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.enters = 0
        self.escapes = 0
        self.nudge_count = 0
        self.result_file: Path | None = None
        self.done_file: Path | None = None
        self.modal_captures = 0
        self.recovered = False

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if "load-buffer" in command:
            prompt = Path(command[-1]).read_text(encoding="utf-8")
            if "literal result file path:" in prompt:
                self.result_file = _path_after(prompt, "literal result file path:")
            if "literal done file path:" in prompt:
                self.done_file = _path_after(prompt, "literal done file path:")
            if "appear to have stopped" in prompt:
                self.nudge_count += 1
            return Completed()
        if "send-keys" in command and "Enter" in command:
            # The idle handler's approval Enter lands only after the loop has
            # idled on the modal; the startup submit Enter comes far earlier.
            if (
                not self.recovered
                and self.modal_captures >= claude_runner.IDLE_POLLS_BEFORE_NUDGE
                and self.result_file is not None
                and self.done_file is not None
            ):
                self.enters += 1
                self.result_file.write_text("SYMPHONY_RESULT: done", encoding="utf-8")
                self.done_file.write_text("", encoding="utf-8")
                self.recovered = True
            return Completed()
        if "send-keys" in command and "Escape" in command:
            self.escapes += 1
            return Completed()
        if "capture-pane" in command:
            if self.recovered:
                return Completed(stdout="working")
            self.modal_captures += 1
            return Completed(stdout=_PERMISSION_MODAL)
        if "has-session" in command:
            return Completed(returncode=0)
        return Completed()


def test_claude_permission_modal_is_approved_then_completes(tmp_path: Path) -> None:
    fake = _PermissionModalThenApprovesTmux()
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("", encoding="utf-8")  # static mtime => transcript idle

    result = run_claude_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
        session_file=transcript,
    )

    # Enter approved the modal once (no Escape); the agent proceeded and
    # completed without being nudged or mislabelled as timed out.
    assert fake.enters == 1
    assert fake.escapes == 0
    assert fake.nudge_count == 0
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.stdout == "SYMPHONY_RESULT: done"


class _PermissionModalPersistsTmux:
    """Pane stays on the permission modal no matter how many times Enter is
    sent -- a prompt that never clears (e.g. a wedged TUI)."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.approval_enters = 0
        self.nudge_count = 0
        self.modal_captures = 0

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if "load-buffer" in command:
            prompt = Path(command[-1]).read_text(encoding="utf-8")
            if "appear to have stopped" in prompt:
                self.nudge_count += 1
            return Completed()
        if "send-keys" in command and "Enter" in command:
            if self.modal_captures >= claude_runner.IDLE_POLLS_BEFORE_NUDGE:
                self.approval_enters += 1
            return Completed()
        if "capture-pane" in command:
            self.modal_captures += 1
            return Completed(stdout=_PERMISSION_MODAL)
        if "has-session" in command:
            return Completed(returncode=0)
        return Completed()


def test_claude_permission_modal_persists_and_aborts(tmp_path: Path) -> None:
    fake = _PermissionModalPersistsTmux()
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("", encoding="utf-8")  # static mtime => transcript idle

    result = run_claude_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,  # never trips run_timeout_ms; modal abort terminates
        sleep=lambda _: None,
        session_file=transcript,
    )

    # Approved MODAL_STUCK_LIMIT times, never nudged, aborted with a clear reason
    # rather than the generic "Agent timed out."
    assert fake.approval_enters == claude_runner.MODAL_STUCK_LIMIT
    assert fake.nudge_count == 0
    assert result.exit_code == -1
    assert result.timed_out is False
    assert "did not clear" in result.stderr


class _QuestionModalThenAutoRepliesTmux:
    """Pane parked on a multi-choice question picker; the idle handler dismisses
    it with Escape and pastes a 'proceed with your recommendations' reply, after
    which the agent completes the protocol."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.escapes = 0
        self.reply_pasted = 0
        self.nudge_count = 0
        self.result_file: Path | None = None
        self.done_file: Path | None = None
        self.recovered = False

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if "load-buffer" in command:
            text = Path(command[-1]).read_text(encoding="utf-8")
            if "literal result file path:" in text:
                self.result_file = _path_after(text, "literal result file path:")
            if "literal done file path:" in text:
                self.done_file = _path_after(text, "literal done file path:")
            if claude_runner.MODAL_QUESTION_REPLY in text:
                self.reply_pasted += 1
            if "appear to have stopped" in text:
                self.nudge_count += 1
            return Completed()
        if "send-keys" in command and "Enter" in command:
            if (
                self.reply_pasted
                and not self.recovered
                and self.result_file is not None
                and self.done_file is not None
            ):
                self.result_file.write_text("SYMPHONY_RESULT: done", encoding="utf-8")
                self.done_file.write_text("", encoding="utf-8")
                self.recovered = True
            return Completed()
        if "send-keys" in command and "Escape" in command:
            self.escapes += 1
            return Completed()
        if "capture-pane" in command:
            return Completed(stdout="working" if self.recovered else _QUESTION_MODAL)
        if "has-session" in command:
            return Completed(returncode=0)
        return Completed()


def test_claude_question_modal_autoreplies_then_completes(tmp_path: Path) -> None:
    fake = _QuestionModalThenAutoRepliesTmux()
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("", encoding="utf-8")  # static mtime => transcript idle

    result = run_claude_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
        session_file=transcript,
    )

    # Escape dismissed the picker once and the proceed-reply was pasted; the
    # agent then completed without being nudged or timed out.
    assert fake.escapes == 1
    assert fake.reply_pasted == 1
    assert fake.nudge_count == 0
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.stdout == "SYMPHONY_RESULT: done"


class _ChangingPaneCompletesTmux:
    """Pane changes on every capture (the working spinner/elapsed timer redraws),
    so the idle detector must never fire; done lands after a while."""

    def __init__(
        self, result_text: str = "SYMPHONY_RESULT: done", complete_after: int = 50
    ):
        self.calls: list[list[str]] = []
        self.captures = 0
        self.complete_after = complete_after
        self.result_text = result_text
        self.result_file: Path | None = None
        self.done_file: Path | None = None
        self.nudge_count = 0

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if "load-buffer" in command:
            prompt = Path(command[-1]).read_text(encoding="utf-8")
            self.result_file = _path_after(prompt, "literal result file path:")
            self.done_file = _path_after(prompt, "literal done file path:")
            if "appear to have stopped" in prompt:
                self.nudge_count += 1
            return Completed()
        if "capture-pane" in command:
            self.captures += 1
            if (
                self.captures >= self.complete_after
                and self.result_file is not None
                and self.done_file is not None
            ):
                self.result_file.write_text(self.result_text, encoding="utf-8")
                self.done_file.write_text("", encoding="utf-8")
            # Ready pattern stays present; the trailing counter changes each call.
            return Completed(stdout=f"bypass permissions on\nworking {self.captures}")
        if "has-session" in command:
            return Completed(returncode=0)
        return Completed()


def test_claude_changing_pane_is_never_nudged(tmp_path: Path) -> None:
    fake = _ChangingPaneCompletesTmux()
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("", encoding="utf-8")  # transcript static; only pane moves

    result = run_claude_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
        session_file=transcript,
    )

    # A working agent (pane redraws every poll) is never treated as idle even with
    # a static transcript, across far more polls than IDLE_POLLS_BEFORE_NUDGE.
    assert fake.captures > claude_runner.IDLE_POLLS_BEFORE_NUDGE
    assert fake.nudge_count == 0
    assert result.exit_code == 0


class _StaticPaneCompletesTmux:
    """Pane never changes (e.g. an alt-screen capture), so only the transcript
    signal can tell working from idle; done lands after a while."""

    def __init__(
        self,
        pane: str = "bypass permissions on",
        result_text: str = "SYMPHONY_RESULT: done",
        complete_after: int = 50,
    ):
        self.calls: list[list[str]] = []
        self.pane = pane
        self.captures = 0
        self.complete_after = complete_after
        self.result_text = result_text
        self.result_file: Path | None = None
        self.done_file: Path | None = None
        self.nudge_count = 0

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if "load-buffer" in command:
            prompt = Path(command[-1]).read_text(encoding="utf-8")
            self.result_file = _path_after(prompt, "literal result file path:")
            self.done_file = _path_after(prompt, "literal done file path:")
            if "appear to have stopped" in prompt:
                self.nudge_count += 1
            return Completed()
        if "capture-pane" in command:
            self.captures += 1
            if (
                self.captures >= self.complete_after
                and self.result_file is not None
                and self.done_file is not None
            ):
                self.result_file.write_text(self.result_text, encoding="utf-8")
                self.done_file.write_text("", encoding="utf-8")
            return Completed(stdout=self.pane)
        if "has-session" in command:
            return Completed(returncode=0)
        return Completed()


def test_claude_static_pane_but_active_transcript_is_never_nudged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _StaticPaneCompletesTmux()
    # Transcript mtime advances every poll (agent is producing events) even though
    # the captured pane is byte-identical -- the complementary signal that keeps an
    # alt-screen working agent from being treated as idle.
    ticks = iter(range(10_000))
    monkeypatch.setattr(
        claude_runner, "_session_file_mtime", lambda _path: float(next(ticks))
    )

    result = run_claude_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        remove_tree=lambda path: None,
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
        session_file=tmp_path / "session.jsonl",
    )

    assert fake.captures > claude_runner.IDLE_POLLS_BEFORE_NUDGE
    assert fake.nudge_count == 0
    assert result.exit_code == 0


def test_claude_runner_does_not_invoke_engine_sh_or_print_mode() -> None:
    source = Path("claude_runner.py").read_text(encoding="utf-8")
    assert "engine.sh" not in source
    assert "claude -p" not in source
