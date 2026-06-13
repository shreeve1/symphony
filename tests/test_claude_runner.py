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
            self.result_file = _path_after(
                prompt, "literal result file path using Bash:"
            )
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
    )

    assert count == 2
    assert calls == [
        ["tmux", "-S", str(sockets[0]), "kill-server"],
        ["tmux", "-S", str(sockets[1]), "kill-server"],
    ]
    assert removed == sockets
    assert f"claude_socket_reaped path={sockets[0]}" in caplog.text
    assert "claude_socket_reap_done count=2" in caplog.text


def test_reap_orphan_claude_sockets_no_sockets_skips_tmux() -> None:
    calls: list[list[str]] = []

    count = reap_orphan_claude_sockets(
        glob_func=lambda pattern: [],
        run_func=lambda command, **kwargs: calls.append(command) or Completed(),
    )

    assert count == 0
    assert calls == []


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
    assert "Nobody can respond to questions" in prompt
    assert "Never ask questions" in prompt
    assert str(fake.result_file) in prompt
    assert str(fake.done_file) in prompt
    assert "Invoke the `dev-build` skill by name" in prompt


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
    assert command[-5:] == [
        "claude",
        "--permission-mode",
        "bypassPermissions",
        "--model",
        "claude-opus-4-8",
    ]
    assert "-p" not in command
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


def test_claude_runner_does_not_invoke_engine_sh_or_print_mode() -> None:
    source = Path("claude_runner.py").read_text(encoding="utf-8")
    assert "engine.sh" not in source
    assert "claude -p" not in source
