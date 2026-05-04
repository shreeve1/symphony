from __future__ import annotations

import signal
import subprocess
from pathlib import Path

import pytest

from agent_runner import AgentRunnerError, run_agent, verify_opencode_support
from config import SymphonyConfig
from plane_poller import CandidateIssue


class Completed:
    def __init__(self, stdout: str = "run --agent", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class FakeProcess:
    def __init__(self, responses: list[object] | None = None):
        self.pid = 4242
        self.returncode = 0
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
        opencode_bin="opencode",
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


def test_verify_opencode_support_requires_run_agent_help() -> None:
    verify_opencode_support("opencode", run_func=lambda *a, **k: Completed())

    with pytest.raises(AgentRunnerError):
        verify_opencode_support("opencode", run_func=lambda *a, **k: Completed(stdout="serve"))


def test_run_agent_sets_env_path_helper_and_process_group(tmp_path: Path) -> None:
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
        run_func=lambda *a, **k: Completed(),
        mkdtemp=lambda **k: str(temp_dir),
        clock=iter([10.0, 10.25]).__next__,
        environ={"PATH": "/usr/bin"},
    )

    assert result.exit_code == 0
    assert result.duration_ms == 250
    assert result.timed_out is False
    assert not temp_dir.exists()
    assert captured["command"] == [
        "opencode",
        "run",
        "--agent",
        "executor-ssh",
        "--dir",
        str(tmp_path),
        "--title",
        "symphony-issue-123",
        "rendered prompt",
    ]
    assert captured["start_new_session"] is True
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["PATH"].startswith(f"{temp_dir}:")
    assert env["SYMPHONY_ISSUE_ID"] == "issue-123"
    assert env["SYMPHONY_PLANE_API_KEY"] == "fake-plane-key-for-tests"


def test_run_agent_timeout_terminates_then_kills_process_group(tmp_path: Path) -> None:
    temp_dir = tmp_path / "temp-helper"
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    timeout = subprocess.TimeoutExpired("opencode", timeout=1)
    process = FakeProcess(responses=[timeout, timeout, ("after kill", "stderr")])
    signals: list[int] = []

    result = run_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        plane_cli_source=helper,
        popen_factory=lambda *a, **k: process,
        run_func=lambda *a, **k: Completed(),
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
