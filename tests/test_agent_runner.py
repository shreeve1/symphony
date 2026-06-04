from __future__ import annotations

import signal
import subprocess
from pathlib import Path

import pytest

import agent_runner as agent_runner_module
from agent_runner import AgentRunnerError, PiAgentAdapter, run_agent, verify_pi_support
from config import SymphonyConfig
from plane_poller import CandidateIssue


class Completed:
    def __init__(self, stdout: str = "pong", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class FakeProcess:
    def __init__(self, responses: list[object] | None = None, returncode: int = 0):
        self.pid = 4242
        self.returncode = returncode
        self.responses = responses or [("stdout", "stderr")]
        self.communicate_calls: list[float | None] = []

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        self.communicate_calls.append(timeout)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response  # type: ignore[return-value]


def _config(tmp_path: Path) -> SymphonyConfig:
    return SymphonyConfig(
        plane_api_url="https://plane.example.test",
        plane_api_key="fake-plane-key-for-tests",
        plane_workspace_slug="homelab",
        plane_project_id="fake-project-id",
        homelab_repo_path=tmp_path,
        pi_bin="pi",
        pi_provider="zai",
        pi_model="glm-5.1:high",
        run_timeout_ms=1000,
    )


def _config_with_model(tmp_path: Path) -> SymphonyConfig:
    return SymphonyConfig(
        plane_api_url="https://plane.example.test",
        plane_api_key="fake-plane-key-for-tests",
        plane_workspace_slug="homelab",
        plane_project_id="fake-project-id",
        homelab_repo_path=tmp_path,
        pi_bin="/usr/local/bin/pi",
        pi_provider="test-provider",
        pi_model="test-model:high",
        run_timeout_ms=1000,
    )


def _issue() -> CandidateIssue:
    return CandidateIssue(
        id="issue-123",
        identifier="HOM-123",
        name="Test issue",
        description="Test description",
        labels=(),
        created_at="2026-05-04T00:00:00+00:00",
    )


def test_verify_pi_support_checks_help_and_probe_with_cwd(tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if len(calls) == 1:
            return Completed(stdout="usage: pi --print --no-session")
        return Completed(stdout="pong")

    verify_pi_support("pi", "zai", "glm-5.1:high", tmp_path, run_func=fake_run)

    assert calls[0][0] == ["pi", "--help"]
    assert calls[0][1]["timeout"] == 30
    assert calls[1][0] == [
        "pi", "--print", "--no-session", "--provider", "zai", "--model", "glm-5.1:high", "ping",
    ]
    assert calls[1][1]["cwd"] == str(tmp_path)
    assert calls[1][1]["timeout"] == 30


@pytest.mark.parametrize("help_text", ["usage: pi --no-session", "usage: pi --print"])
def test_verify_pi_support_requires_print_and_no_session(help_text: str, tmp_path: Path) -> None:
    with pytest.raises(AgentRunnerError, match="--print --no-session"):
        verify_pi_support(
            "pi",
            "zai",
            "glm-5.1:high",
            tmp_path,
            run_func=lambda *a, **k: Completed(stdout=help_text),
        )


def test_verify_pi_support_rejects_probe_nonzero(tmp_path: Path) -> None:
    responses = iter([
        Completed(stdout="usage: pi --print --no-session"),
        Completed(stderr="bad auth", returncode=2),
    ])

    with pytest.raises(AgentRunnerError, match="exit code 2"):
        verify_pi_support(
            "pi", "zai", "glm-5.1:high", tmp_path, run_func=lambda *a, **k: next(responses)
        )


@pytest.mark.parametrize("stdout", ["", "   \n"])
def test_verify_pi_support_rejects_empty_probe_stdout(stdout: str, tmp_path: Path) -> None:
    responses = iter([
        Completed(stdout="usage: pi --print --no-session"),
        Completed(stdout=stdout),
    ])

    with pytest.raises(AgentRunnerError, match="empty stdout"):
        verify_pi_support(
            "pi", "zai", "glm-5.1:high", tmp_path, run_func=lambda *a, **k: next(responses)
        )


def test_verify_pi_support_wraps_oserror(tmp_path: Path) -> None:
    def fake_run(*args, **kwargs):
        raise PermissionError("not executable")

    with pytest.raises(AgentRunnerError, match="could not be executed"):
        verify_pi_support("pi", "zai", "glm-5.1:high", tmp_path, run_func=fake_run)


def test_verify_pi_support_wraps_help_timeout(tmp_path: Path) -> None:
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    with pytest.raises(AgentRunnerError, match="help check timed out"):
        verify_pi_support("pi", "zai", "glm-5.1:high", tmp_path, run_func=fake_run)


def test_verify_pi_support_wraps_probe_timeout(tmp_path: Path) -> None:
    responses = iter([
        Completed(stdout="usage: pi --print --no-session"),
        subprocess.TimeoutExpired(["pi"], 30),
    ])

    def fake_run(*args, **kwargs):
        response = next(responses)
        if isinstance(response, BaseException):
            raise response
        return response

    with pytest.raises(AgentRunnerError, match="probe timed out"):
        verify_pi_support("pi", "zai", "glm-5.1:high", tmp_path, run_func=fake_run)


def test_pi_agent_adapter_delegates_to_pi_runner(monkeypatch, tmp_path: Path) -> None:
    calls = {}

    def fake_run_agent(config, issue, rendered_prompt):
        calls["args"] = (config, issue, rendered_prompt)
        return "agent-result"

    monkeypatch.setattr(agent_runner_module, "run_agent", fake_run_agent)
    config = _config(tmp_path)
    issue = _issue()

    result = PiAgentAdapter(config)(issue, "rendered prompt")

    assert result == "agent-result"
    assert calls["args"] == (config, issue, "rendered prompt")


def test_run_agent_sets_pi_argv_env_cwd_and_process_group(tmp_path: Path) -> None:
    temp_dir = tmp_path / "temp-helper"
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    captured: dict[str, object] = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return FakeProcess()

    result = run_agent(
        _config(tmp_path),
        _issue(),
        "rendered prompt",
        plane_cli_source=helper,
        popen_factory=fake_popen,
        mkdtemp=lambda **k: str(temp_dir),
        clock=iter([10.0, 10.25]).__next__,
        environ={
            "PATH": "/usr/bin",
            "HOME": "/home/james",
            "TERM": "xterm-256color",
            "SECRET_LEAK": "should-not-appear",
            "PLANE_API_KEY": "leaked-key",
            "TELEGRAM_BOT_TOKEN": "tok-123",
            "TELEGRAM_CHAT_ID": "chat-456",
            "ZAI_API_KEY": "zai-secret",
            "CLIP" + "ROXY_API_KEY": "cliproxy-secret",
            "PI_OFFLINE": "1",
            "PI_CODING_AGENT_DIR": "/tmp/pi-config",
            "PI_CODING_AGENT_SESSION_DIR": "/tmp/pi-sessions",
        },
    )

    assert result.exit_code == 0
    assert result.duration_ms == 250
    assert result.timed_out is False
    assert not temp_dir.exists()
    assert captured["command"] == [
        "pi",
        "--print",
        "--no-session",
        "--provider",
        "zai",
        "--model",
        "glm-5.1:high",
        "rendered prompt",
    ]
    assert captured["cwd"] == str(tmp_path)
    assert captured["start_new_session"] is True
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["PATH"].startswith(f"{temp_dir}:")
    assert env["SYMPHONY_ISSUE_ID"] == "issue-123"
    assert env["SYMPHONY_PLANE_FRONTEND_URL"] == ""
    assert env["PLANE_DASHBOARD_URL"] == ""
    assert env["SYMPHONY_PLANE_API_KEY"] == "fake-plane-key-for-tests"
    assert env["PYTHONPATH"] == str(Path(__file__).parents[1])
    assert env["ZAI_API_KEY"] == "zai-secret"
    assert env["PI_OFFLINE"] == "1"
    assert env["PI_CODING_AGENT_DIR"] == "/tmp/pi-config"
    assert env["PI_CODING_AGENT_SESSION_DIR"] == "/tmp/pi-sessions"
    assert "CLIP" + "ROXY_API_KEY" not in env
    assert "SECRET_LEAK" not in env
    assert env.get("HOME") == "/home/james"
    assert env.get("TELEGRAM_BOT_TOKEN") == "tok-123"
    assert env.get("TELEGRAM_CHAT_ID") == "chat-456"
    # Defense-in-depth against ANSI color trace in captured stderr: inbound
    # TERM must be overridden, NO_COLOR forced.
    assert env.get("TERM") == "dumb"
    assert env.get("NO_COLOR") == "1"


def test_run_agent_uses_configured_provider_model_and_logs(caplog, tmp_path: Path) -> None:
    caplog.set_level("INFO", logger="agent_runner")
    temp_dir = tmp_path / "temp-helper"
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    captured: dict[str, object] = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        return FakeProcess()

    run_agent(
        _config_with_model(tmp_path),
        _issue(),
        "rendered prompt",
        plane_cli_source=helper,
        popen_factory=fake_popen,
        mkdtemp=lambda **k: str(temp_dir),
        environ={"PATH": "/usr/bin"},
    )

    assert captured["command"] == [
        "/usr/local/bin/pi",
        "--print",
        "--no-session",
        "--provider",
        "test-provider",
        "--model",
        "test-model:high",
        "rendered prompt",
    ]
    assert "pi_dispatch issue_id=issue-123 provider=test-provider model=test-model:high" in caplog.text


def test_run_agent_silent_zero_exit_becomes_failure(tmp_path: Path) -> None:
    temp_dir = tmp_path / "temp-helper"
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")

    result = run_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        plane_cli_source=helper,
        popen_factory=lambda *a, **k: FakeProcess(responses=[("", "")], returncode=0),
        mkdtemp=lambda **k: str(temp_dir),
        environ={"PATH": "/usr/bin"},
    )

    assert result.exit_code == 137
    assert result.timed_out is False
    assert "empty stdout/stderr" in result.stderr


def test_run_agent_non_silent_zero_exit_stays_success(tmp_path: Path) -> None:
    temp_dir = tmp_path / "temp-helper"
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")

    result = run_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        plane_cli_source=helper,
        popen_factory=lambda *a, **k: FakeProcess(responses=[("ok", "")], returncode=0),
        mkdtemp=lambda **k: str(temp_dir),
        environ={"PATH": "/usr/bin"},
    )

    assert result.exit_code == 0
    assert result.stdout == "ok"


def test_run_agent_timeout_terminates_then_kills_process_group(tmp_path: Path) -> None:
    temp_dir = tmp_path / "temp-helper"
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    timeout = subprocess.TimeoutExpired("pi", timeout=1)
    process = FakeProcess(responses=[timeout, timeout, ("after kill", "stderr")])
    signals: list[int] = []

    result = run_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        plane_cli_source=helper,
        popen_factory=lambda *a, **k: process,
        mkdtemp=lambda **k: str(temp_dir),
        kill_process_group=lambda pid, sig: signals.append(sig),
        clock=iter([1.0, 2.2]).__next__,
        environ={"PATH": "/usr/bin"},
    )

    assert result.timed_out is True
    assert result.exit_code == -1
    assert result.stdout == "after kill"
    assert signals == [signal.SIGTERM, signal.SIGKILL]
    assert process.communicate_calls == [1.0, 5, None]
    assert not temp_dir.exists()
