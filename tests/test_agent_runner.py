from __future__ import annotations

import asyncio
import io
import json
import os
import signal
import subprocess
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest

import agent_runner as agent_runner_module
import main
from agent_runner import (
    AgentResult,
    AgentRunnerError,
    PiAgentAdapter,
    RoutingAgentAdapter,
    reap_orphan_rpc_processes,
    run_agent,
    run_pi_rpc_agent,
    run_remote_agent,
    verify_pi_rpc_support,
    verify_pi_support,
)
from config import ProjectBinding, RemotePolicy, SymphonyConfig
from plane_poller import CandidateIssue
from redispatch_core import STALL_WATCHDOG_SENTINEL

steer_queue = import_module("web.api.steer_queue")


class Completed:
    def __init__(self, stdout: str = "pong", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class FakeRpcProcess:
    def __init__(self, lines: list[str], returncode: int = 0):
        self.pid = 4343
        self.returncode = returncode
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("".join(lines))
        self.stderr = io.StringIO("")
        self.wait_calls: list[float | None] = []

    def poll(self) -> int | None:
        if self.stdout.tell() == len(self.stdout.getvalue()):
            return self.returncode
        return None

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        return self.returncode

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        return self.stdout.read(), self.stderr.read()


def _clock(values: list[float]):
    items = iter(values)
    last = values[-1]

    def tick() -> float:
        nonlocal last
        last = next(items, last)
        return last

    return tick


def _stall_read_line(lines: list[str | None]):
    index = 0

    def read_line(timeout: float) -> tuple[str | None, bool]:
        nonlocal index
        if index >= len(lines):
            return None, True
        line = lines[index]
        index += 1
        return line, False

    return read_line


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


def _podium_config(tmp_path: Path) -> SymphonyConfig:
    base = _config(tmp_path)
    return SymphonyConfig(
        plane_api_url=base.plane_api_url,
        plane_api_key=base.plane_api_key,
        plane_workspace_slug=base.plane_workspace_slug,
        plane_project_id=base.plane_project_id,
        homelab_repo_path=tmp_path,
        pi_bin=base.pi_bin,
        pi_provider=base.pi_provider,
        pi_model=base.pi_model,
        run_timeout_ms=base.run_timeout_ms,
        bindings=(
            ProjectBinding(
                name="podium-test",
                plane_project_id=base.plane_project_id,
                repo_path=tmp_path,
                base_branch="main",
                tracker_contract=base.bindings[0].tracker_contract,
                tracker="podium",
            ),
        ),
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


def test_build_pi_command_print_mode_uses_skill_parent_and_prompt() -> None:
    command = agent_runner_module._build_pi_command(
        "/usr/local/bin/pi",
        "provider",
        "model:high",
        skill_source="/home/james/.claude/skills/diagnose/SKILL.md",
        rendered_prompt="do work",
    )

    assert command == [
        "/usr/local/bin/pi",
        "--print",
        "--no-session",
        "--provider",
        "provider",
        "--model",
        "model:high",
        "--skill",
        "/home/james/.claude/skills/diagnose",
        "do work",
    ]


def test_build_pi_command_rpc_mode_uses_session_without_prompt() -> None:
    command = agent_runner_module._build_pi_command(
        "pi",
        "provider",
        "model",
        session_id="session-123",
    )

    assert command == [
        "pi",
        "--mode",
        "rpc",
        "--provider",
        "provider",
        "--model",
        "model",
        "--session-id",
        "session-123",
    ]


def test_silent_exit_result_returns_failure_only_for_empty_output() -> None:
    message = "pi exited 0 with empty stdout/stderr"
    silent = agent_runner_module._silent_exit_result(
        issue_id="issue-123",
        exit_code=0,
        duration_ms=25,
        stdout="\n",
        stderr=" ",
        message=message,
        log_event="pi_silent_exit",
    )
    noisy = agent_runner_module._silent_exit_result(
        issue_id="issue-123",
        exit_code=0,
        duration_ms=25,
        stdout="ok",
        stderr="",
        message=message,
        log_event="pi_silent_exit",
    )

    assert silent == AgentResult(137, 25, False, "\n", message)
    assert noisy is None


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(path), "init", "-b", "main"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@test"], check=True
    )
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    (path / "README.md").write_text("# test\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "initial"], check=True)


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
        "pi",
        "--print",
        "--no-session",
        "--provider",
        "zai",
        "--model",
        "glm-5.1:high",
        "ping",
    ]
    assert calls[1][1]["cwd"] == str(tmp_path)
    assert calls[1][1]["timeout"] == 30


@pytest.mark.parametrize("help_text", ["usage: pi --no-session", "usage: pi --print"])
def test_verify_pi_support_requires_print_and_no_session(
    help_text: str, tmp_path: Path
) -> None:
    with pytest.raises(AgentRunnerError, match="--print --no-session"):
        verify_pi_support(
            "pi",
            "zai",
            "glm-5.1:high",
            tmp_path,
            run_func=lambda *a, **k: Completed(stdout=help_text),
        )


def test_verify_pi_support_rejects_probe_nonzero(tmp_path: Path) -> None:
    responses = iter(
        [
            Completed(stdout="usage: pi --print --no-session"),
            Completed(stderr="bad auth", returncode=2),
        ]
    )

    with pytest.raises(AgentRunnerError, match="exit code 2"):
        verify_pi_support(
            "pi",
            "zai",
            "glm-5.1:high",
            tmp_path,
            run_func=lambda *a, **k: next(responses),
        )


@pytest.mark.parametrize("stdout", ["", "   \n"])
def test_verify_pi_support_rejects_empty_probe_stdout(
    stdout: str, tmp_path: Path
) -> None:
    responses = iter(
        [
            Completed(stdout="usage: pi --print --no-session"),
            Completed(stdout=stdout),
        ]
    )

    with pytest.raises(AgentRunnerError, match="empty stdout"):
        verify_pi_support(
            "pi",
            "zai",
            "glm-5.1:high",
            tmp_path,
            run_func=lambda *a, **k: next(responses),
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
    responses = iter(
        [
            Completed(stdout="usage: pi --print --no-session"),
            subprocess.TimeoutExpired(["pi"], 30),
        ]
    )

    def fake_run(*args, **kwargs):
        response = next(responses)
        if isinstance(response, BaseException):
            raise response
        return response

    with pytest.raises(AgentRunnerError, match="probe timed out"):
        verify_pi_support("pi", "zai", "glm-5.1:high", tmp_path, run_func=fake_run)


def test_probe_binding_retries_pi_timeout_then_succeeds(
    monkeypatch, tmp_path: Path
) -> None:
    calls = []
    sleeps = []
    config = _config(tmp_path)

    def fake_verify(*args):
        calls.append(args)
        if len(calls) == 1:
            raise AgentRunnerError("timeout")

    monkeypatch.setattr(main, "verify_pi_support", fake_verify)
    monkeypatch.setattr(main.time, "sleep", lambda seconds: sleeps.append(seconds))

    assert main._probe_binding(config, config.bindings[0]) is True
    assert len(calls) == 2
    assert sleeps == [main.PI_PROBE_RETRY_DELAY_SECONDS]


def test_probe_binding_permanent_pi_failure_logs_and_skips(
    monkeypatch, tmp_path: Path, caplog
) -> None:
    calls = []
    config = _config(tmp_path)

    def fake_verify(*args):
        calls.append(args)
        raise AgentRunnerError("bad pi")

    monkeypatch.setattr(main, "verify_pi_support", fake_verify)
    monkeypatch.setattr(main.time, "sleep", lambda seconds: None)

    with caplog.at_level("ERROR", logger=main.__name__):
        assert main._probe_binding(config, config.bindings[0]) is False

    assert len(calls) == main.PI_PROBE_MAX_ATTEMPTS
    assert "pi_probe_failed_permanently binding=default" in caplog.text


def test_run_bindings_loop_skips_failed_probe_without_blocking_other_binding(
    monkeypatch, caplog
) -> None:
    calls = []

    class StopLoop(Exception):
        pass

    class FakeBinding:
        pi_mode = "one-shot"
        binding_type = "infra"

        def __init__(self, name: str):
            self.name = name

    class FakeConfig:
        bindings = (FakeBinding("bad"), FakeBinding("good"))

    class FakeRuntimeConfig:
        homelab_repo_path = Path("/tmp/good")

        @property
        def bindings(self):
            return (FakeBinding("good"),)

    class FakeAdapter:
        contract = None

    def fake_probe(config, binding):
        calls.append(("probe", binding.name))
        return binding.name != "bad"

    def fake_build(config, binding):
        calls.append(("build", binding.name))
        return main.BindingRuntime(
            name=binding.name,
            config=cast(Any, FakeRuntimeConfig()),
            transport=None,
            adapter=cast(Any, FakeAdapter()),
            agent_adapter=cast(Any, "agent"),
            binding=binding,
        )

    async def fake_reconcile_startup(config, adapter, *, notifier=None, binding=None):
        calls.append(("reconcile", cast(Any, binding).name))
        return 0

    async def fake_run_loop(config, adapter, **kwargs):
        calls.append(("run-loop", kwargs["binding"].name))
        raise StopLoop

    monkeypatch.setattr(main, "reap_orphan_claude_sockets", lambda **kwargs: None)
    monkeypatch.setattr(main, "verify_claude_support", lambda: None)
    monkeypatch.setattr(main, "reap_orphan_rpc_processes", lambda: None)
    monkeypatch.setattr(main, "_probe_binding", fake_probe)
    monkeypatch.setattr(main, "build_binding_runtime", fake_build)
    monkeypatch.setattr(main, "reconcile_startup", fake_reconcile_startup)
    monkeypatch.setattr(main, "run_loop", fake_run_loop)

    with caplog.at_level("WARNING", logger=main.__name__), pytest.raises(StopLoop):
        asyncio.run(main.run_bindings_loop(cast(Any, FakeConfig())))

    assert calls == [
        ("probe", "bad"),
        ("probe", "good"),
        ("build", "good"),
        ("reconcile", "good"),
        ("run-loop", "good"),
    ]
    assert "binding_skipped_after_probe_failure binding=bad" in caplog.text


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


def test_routing_agent_adapter_routes_by_resolved_agent(tmp_path: Path) -> None:
    seen: list[str] = []

    def pi_adapter_fn(issue, prompt):
        seen.append("pi")
        return AgentResult(0, 1, False)

    def claude_adapter_fn(issue, prompt):
        seen.append("claude")
        return AgentResult(0, 1, False)

    binding = ProjectBinding(
        name="test",
        plane_project_id="project",
        repo_path=tmp_path,
        base_branch="main",
        tracker_contract=_config(tmp_path).bindings[0].tracker_contract,
    )
    router = RoutingAgentAdapter(
        binding,
        pi_adapter=pi_adapter_fn,
        claude_adapter=claude_adapter_fn,
    )

    router(_issue(), "prompt")
    router(
        CandidateIssue(
            id="issue-456",
            identifier="HOM-456",
            name="Claude issue",
            description="Test description",
            labels=("agent:claude",),
            created_at="2026-05-04T00:00:00+00:00",
        ),
        "prompt",
    )

    assert seen == ["pi", "claude"]


def test_routing_agent_adapter_routes_remote_claude_to_claude_adapter(
    tmp_path: Path,
) -> None:
    seen: list[str] = []
    binding = ProjectBinding(
        name="remote",
        plane_project_id="project",
        repo_path=tmp_path,
        base_branch="main",
        tracker_contract=_config(tmp_path).bindings[0].tracker_contract,
        default_agent="claude",
        remote=RemotePolicy(host="host", user="user"),
    )
    router = RoutingAgentAdapter(
        binding,
        pi_adapter=lambda issue, prompt: seen.append("pi") or AgentResult(0, 1, False),
        claude_adapter=lambda issue, prompt: (
            seen.append("claude") or AgentResult(0, 1, False)
        ),
        remote_adapter=lambda issue, prompt: (
            seen.append("remote") or AgentResult(0, 1, False)
        ),
    )

    router(_issue(), "prompt")

    assert seen == ["claude"]


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
    assert env["SYMPHONY_TRACKER_API_URL"] == "https://plane.example.test"
    assert env["SYMPHONY_TRACKER_FRONTEND_URL"] == ""
    assert env["SYMPHONY_TRACKER_DASHBOARD_URL"] == ""
    assert env["SYMPHONY_TRACKER_API_KEY"] == "fake-plane-key-for-tests"
    assert env["SYMPHONY_TRACKER_PROJECT_ID"] == "fake-project-id"
    assert env["SYMPHONY_TRACKER_WORKSPACE_SLUG"] == "homelab"
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
    assert "TELEGRAM_BOT_TOKEN" not in env
    assert "TELEGRAM_CHAT_ID" not in env
    assert "SYMPHONY_ISSUE_TELEGRAM_NOTIFICATIONS" not in env
    # Defense-in-depth against ANSI color trace in captured stderr: inbound
    # TERM must be overridden, NO_COLOR forced.
    assert env.get("TERM") == "dumb"
    assert env.get("NO_COLOR") == "1"


def test_run_agent_passes_telegram_env_only_when_issue_notifications_enabled(
    tmp_path: Path,
) -> None:
    temp_dir = tmp_path / "temp-helper"
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    captured: dict[str, object] = {}

    def fake_popen(command, **kwargs):
        captured.update(kwargs)
        return FakeProcess()

    config = SymphonyConfig(
        plane_api_url="https://plane.example.test",
        plane_api_key="fake-plane-key-for-tests",
        plane_workspace_slug="homelab",
        plane_project_id="fake-project-id",
        homelab_repo_path=tmp_path,
        pi_bin="pi",
        run_timeout_ms=1000,
        issue_telegram_notifications_enabled=True,
    )

    run_agent(
        config,
        _issue(),
        "rendered prompt",
        plane_cli_source=helper,
        popen_factory=fake_popen,
        mkdtemp=lambda **k: str(temp_dir),
        environ={
            "PATH": "/usr/bin",
            "TELEGRAM_BOT_TOKEN": "tok-123",
            "TELEGRAM_CHAT_ID": "chat-456",
        },
    )

    env = captured["env"]
    assert isinstance(env, dict)
    assert env["TELEGRAM_BOT_TOKEN"] == "tok-123"
    assert env["TELEGRAM_CHAT_ID"] == "chat-456"
    assert env["SYMPHONY_ISSUE_TELEGRAM_NOTIFICATIONS"] == "1"


def test_run_agent_omits_plane_env_and_helper_for_podium_binding(
    tmp_path: Path,
) -> None:
    temp_dir = tmp_path / "temp-helper"
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    captured: dict[str, object] = {}
    copied: list[tuple[Path, Path]] = []

    def fake_popen(command, **kwargs):
        captured.update(kwargs)
        return FakeProcess()

    result = run_agent(
        _podium_config(tmp_path),
        _issue(),
        "rendered prompt",
        plane_cli_source=helper,
        popen_factory=fake_popen,
        mkdtemp=lambda **k: str(temp_dir),
        copy_file=lambda src, dst: copied.append((src, dst)),
        environ={"PATH": "/usr/bin", "HOME": "/home/james"},
    )

    assert result.exit_code == 0
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["SYMPHONY_ISSUE_ID"] == "issue-123"
    assert "SYMPHONY_TRACKER_API_KEY" not in env
    assert "SYMPHONY_TRACKER_API_URL" not in env
    assert "SYMPHONY_TRACKER_FRONTEND_URL" not in env
    assert "SYMPHONY_TRACKER_DASHBOARD_URL" not in env
    assert "SYMPHONY_TRACKER_PROJECT_ID" not in env
    assert "SYMPHONY_TRACKER_WORKSPACE_SLUG" not in env
    assert "SYMPHONY_PLANE_API_KEY" not in env
    assert "SYMPHONY_PLANE_API_URL" not in env
    assert "SYMPHONY_PLANE_FRONTEND_URL" not in env
    assert "SYMPHONY_PLANE_PROJECT_ID" not in env
    assert "SYMPHONY_PLANE_WORKSPACE_SLUG" not in env
    assert "PLANE_DASHBOARD_URL" not in env
    assert copied == []


def test_run_agent_uses_worktree_cwd_when_issue_opted_in(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    temp_dir = tmp_path / "temp-helper"
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    captured: dict[str, object] = {}
    issue = CandidateIssue(
        id="42",
        identifier="HOM-42",
        name="Worktree issue",
        description="Test description",
        labels=(),
        created_at="2026-05-04T00:00:00+00:00",
        worktree_active=True,
        base_branch="main",
        binding_name="trading",
    )

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return FakeProcess()

    result = run_agent(
        _config(repo),
        issue,
        "rendered prompt",
        plane_cli_source=helper,
        popen_factory=fake_popen,
        mkdtemp=lambda **k: str(temp_dir),
        environ={"PATH": "/usr/bin"},
    )

    expected_worktree = (repo / "worktrees" / "trading" / "42").resolve()
    assert result.exit_code == 0
    assert captured["cwd"] == str(expected_worktree)
    assert expected_worktree.is_dir()
    branches = subprocess.run(
        ["git", "-C", str(repo), "branch", "--list"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "podium/trading/42" in branches


def test_run_pi_rpc_agent_uses_worktree_cwd_when_issue_opted_in(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    temp_dir = tmp_path / "temp-helper"
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    captured: dict[str, object] = {}
    process = FakeRpcProcess(
        [
            json.dumps({"type": "message_update", "delta": "SYMPHONY_RESULT: done\n"})
            + "\n",
            json.dumps({"type": "agent_end", "exit_code": 0}) + "\n",
        ]
    )
    issue = CandidateIssue(
        id="42",
        identifier="HOM-42",
        name="Worktree issue",
        description="Test description",
        labels=(),
        created_at="2026-05-04T00:00:00+00:00",
        worktree_active=True,
        base_branch="main",
        binding_name="trading",
    )

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return process

    result = run_pi_rpc_agent(
        _config(repo),
        issue,
        "rendered prompt",
        plane_cli_source=helper,
        popen_factory=fake_popen,
        mkdtemp=lambda **k: str(temp_dir),
        clock=lambda: 10.0,
        environ={"PATH": "/usr/bin"},
    )

    expected_worktree = (repo / "worktrees" / "trading" / "42").resolve()
    assert result.exit_code == 0
    assert captured["cwd"] == str(expected_worktree)
    assert expected_worktree.is_dir()


def test_run_agent_uses_configured_provider_model_and_logs(
    caplog, tmp_path: Path
) -> None:
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
    assert (
        "pi_dispatch issue_id=issue-123 provider=test-provider model=test-model:high"
        in caplog.text
    )


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


def test_run_pi_rpc_agent_sends_prompt_and_returns_final_text(tmp_path: Path) -> None:
    temp_dir = tmp_path / "temp-helper"
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    captured: dict[str, object] = {}
    process = FakeRpcProcess(
        [
            json.dumps({"type": "message_update", "delta": "SYMPHONY_RESULT: done\n"})
            + "\n",
            json.dumps({"type": "message_update", "delta": "SYMPHONY_SUMMARY: ok"})
            + "\n",
            json.dumps({"type": "agent_end", "exit_code": 0}) + "\n",
        ]
    )

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return process

    issue = _issue()
    result = run_pi_rpc_agent(
        _config_with_model(tmp_path),
        issue,
        "rendered prompt",
        plane_cli_source=helper,
        popen_factory=fake_popen,
        mkdtemp=lambda **k: str(temp_dir),
        clock=lambda: 10.0,
        environ={"PATH": "/usr/bin"},
    )

    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.stdout == "SYMPHONY_RESULT: done\nSYMPHONY_SUMMARY: ok"
    command = captured["command"]
    assert isinstance(command, list)
    assert command[:7] == [
        "/usr/local/bin/pi",
        "--mode",
        "rpc",
        "--provider",
        "test-provider",
        "--model",
        "test-model:high",
    ]
    assert "--session-id" in command
    assert "--no-session" not in command
    assert "--continue" not in command
    assert "-c" not in command
    assert captured["stdin"] is subprocess.PIPE
    assert captured["cwd"] == str(tmp_path)
    sent = json.loads(process.stdin.getvalue().strip())
    assert sent == {"type": "prompt", "message": "rendered prompt"}


def test_run_pi_rpc_agent_forwards_queued_steer(tmp_path: Path) -> None:
    temp_dir = tmp_path / "temp-helper"
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    process = FakeRpcProcess([json.dumps({"type": "agent_end", "exit_code": 0}) + "\n"])
    environ = {"PATH": "/usr/bin", "SYMPHONY_RUNTIME_DIR": str(tmp_path)}
    steer_queue.write_steer_record(
        "77",
        _issue().id,
        kind="steer",
        message="switch to safer approach",
        environ=environ,
    )
    issue = CandidateIssue(
        id="issue-123",
        identifier="HOM-123",
        name="Test issue",
        description="Test description",
        labels=(),
        created_at="2026-05-04T00:00:00+00:00",
        active_run_id="77",
    )

    result = run_pi_rpc_agent(
        _config(tmp_path),
        issue,
        "prompt",
        plane_cli_source=helper,
        popen_factory=lambda *a, **k: process,
        mkdtemp=lambda **k: str(temp_dir),
        kill_process_group=lambda pid, sig: None,
        clock=lambda: 0.0,
        environ=environ,
    )

    assert result.exit_code == 0
    commands = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
    assert commands[0] == {"type": "prompt", "message": "prompt"}
    assert {"type": "steer", "message": "switch to safer approach"} in commands


def test_run_pi_rpc_agent_forwards_queued_abort(tmp_path: Path) -> None:
    temp_dir = tmp_path / "temp-helper"
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    process = FakeRpcProcess([json.dumps({"type": "agent_end", "exit_code": 0}) + "\n"])
    environ = {"PATH": "/usr/bin", "SYMPHONY_RUNTIME_DIR": str(tmp_path)}
    steer_queue.write_steer_record("78", _issue().id, kind="abort", environ=environ)
    issue = CandidateIssue(
        id="issue-123",
        identifier="HOM-123",
        name="Test issue",
        description="Test description",
        labels=(),
        created_at="2026-05-04T00:00:00+00:00",
        active_run_id="78",
    )

    run_pi_rpc_agent(
        _config(tmp_path),
        issue,
        "prompt",
        plane_cli_source=helper,
        popen_factory=lambda *a, **k: process,
        mkdtemp=lambda **k: str(temp_dir),
        kill_process_group=lambda pid, sig: None,
        clock=lambda: 0.0,
        environ=environ,
    )

    commands = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
    assert {"type": "abort"} in commands


def test_drain_rpc_events_spools_assistant_deltas(tmp_path: Path) -> None:
    """With a spool path, the drain loop mirrors assistant deltas to a local
    file so the web tailer can stream remote runs (ADR-0019)."""
    process = FakeRpcProcess(
        [
            json.dumps({"type": "message_update", "delta": "Working"}) + "\n",
            json.dumps({"type": "message_update", "delta": " on it"}) + "\n",
            json.dumps({"type": "agent_end", "exit_code": 0}) + "\n",
        ]
    )
    read_line, close_reader = agent_runner_module._rpc_line_reader(process)
    spool = tmp_path / "tail" / "55.log"

    drain = agent_runner_module._drain_rpc_events(
        process,
        1_000_000.0,
        "55",
        read_queued_steers=None,
        steer_offset=0,
        read_line=read_line,
        close_reader=close_reader,
        kill_process_group=lambda pid, sig: None,
        clock=lambda: 0.0,
        source_env={},
        spool_path=spool,
    )

    assert drain.event_exit_code == 0
    assert spool.read_text() == "Working on it"


def test_drain_rpc_events_separates_text_blocks(tmp_path: Path) -> None:
    """Distinct assistant text blocks (narration between tool calls) are joined
    with a blank line, not mashed together ("explore.This is")."""

    def text_start() -> str:
        return (
            json.dumps(
                {
                    "type": "message_update",
                    "assistantMessageEvent": {"type": "text_start"},
                }
            )
            + "\n"
        )

    def text_delta(s: str) -> str:
        return (
            json.dumps(
                {
                    "type": "message_update",
                    "assistantMessageEvent": {"type": "text_delta", "delta": s},
                }
            )
            + "\n"
        )

    process = FakeRpcProcess(
        [
            text_start(),
            text_delta("Let me explore."),
            json.dumps({"type": "message_end", "message": {}}) + "\n",
            text_start(),
            text_delta("This is a frontend bug."),
            json.dumps({"type": "agent_end", "exit_code": 0}) + "\n",
        ]
    )
    read_line, close_reader = agent_runner_module._rpc_line_reader(process)

    drain = agent_runner_module._drain_rpc_events(
        process,
        1_000_000.0,
        "55",
        read_queued_steers=None,
        steer_offset=0,
        read_line=read_line,
        close_reader=close_reader,
        kill_process_group=lambda pid, sig: None,
        clock=lambda: 0.0,
        source_env={},
    )

    assert "".join(drain.assistant_parts) == (
        "Let me explore.\n\nThis is a frontend bug."
    )


def test_drain_rpc_events_caps_spool_size(monkeypatch, tmp_path: Path) -> None:
    """The spool stops growing past the cap (tmpfs safety) while the drain
    result is unaffected (ADR-0019)."""
    monkeypatch.setattr(agent_runner_module, "TAIL_SPOOL_MAX_BYTES", 10)
    process = FakeRpcProcess(
        [
            json.dumps({"type": "message_update", "delta": "x" * 50}) + "\n",
            json.dumps({"type": "message_update", "delta": "after the cap"}) + "\n",
            json.dumps({"type": "agent_end", "exit_code": 0}) + "\n",
        ]
    )
    read_line, close_reader = agent_runner_module._rpc_line_reader(process)
    spool = tmp_path / "tail" / "77.log"

    drain = agent_runner_module._drain_rpc_events(
        process,
        1_000_000.0,
        "77",
        read_queued_steers=None,
        steer_offset=0,
        read_line=read_line,
        close_reader=close_reader,
        kill_process_group=lambda pid, sig: None,
        clock=lambda: 0.0,
        source_env={},
        spool_path=spool,
    )

    text = spool.read_text()
    assert "x" * 50 in text  # the delta that crosses the cap is still written
    assert "truncated" in text
    assert "after the cap" not in text  # writes stop once capped
    # Drain output is unaffected by the spool cap.
    assert drain.event_exit_code == 0
    assert "after the cap" in "".join(drain.assistant_parts)


def test_drain_rpc_events_stalls_after_silence() -> None:
    process = FakeRpcProcess([])
    signals: list[int] = []

    drain = agent_runner_module._drain_rpc_events(
        process,
        100.0,
        "run-1",
        read_queued_steers=None,
        steer_offset=0,
        read_line=_stall_read_line([None]),
        close_reader=lambda: None,
        kill_process_group=lambda pid, sig: signals.append(sig),
        clock=_clock([0.0, 0.0, 1.1]),
        source_env={},
        stall_timeout_s=1.0,
    )

    assert drain.stalled is True
    assert drain.timed_out is False
    assert signals == [signal.SIGTERM]
    assert json.loads(process.stdin.getvalue().strip()) == {"type": "abort"}


def test_drain_rpc_events_sparse_events_do_not_stall() -> None:
    process = FakeRpcProcess([])

    drain = agent_runner_module._drain_rpc_events(
        process,
        100.0,
        "run-1",
        read_queued_steers=None,
        steer_offset=0,
        read_line=_stall_read_line(
            [
                None,
                json.dumps({"type": "message_update", "delta": "still here"}),
                json.dumps({"type": "agent_end", "exit_code": 0}),
            ]
        ),
        close_reader=lambda: None,
        kill_process_group=lambda pid, sig: None,
        clock=_clock([0.0, 0.0, 0.9, 0.9, 1.8, 1.8]),
        source_env={},
        stall_timeout_s=1.0,
    )

    assert drain.stalled is False
    assert drain.event_exit_code == 0
    assert "".join(drain.assistant_parts) == "still here"


def test_drain_rpc_events_deadline_wins_over_stall() -> None:
    process = FakeRpcProcess([])

    drain = agent_runner_module._drain_rpc_events(
        process,
        1.0,
        "run-1",
        read_queued_steers=None,
        steer_offset=0,
        read_line=_stall_read_line([None]),
        close_reader=lambda: None,
        kill_process_group=lambda pid, sig: None,
        clock=_clock([0.0, 2.0]),
        source_env={},
        stall_timeout_s=1.0,
    )

    assert drain.timed_out is True
    assert drain.stalled is False


def test_run_pi_rpc_agent_stall_returns_watchdog_sentinel(
    monkeypatch, tmp_path: Path
) -> None:
    temp_dir = tmp_path / "temp-helper"
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    process = FakeRpcProcess([])
    signals: list[int] = []
    monkeypatch.setattr(
        agent_runner_module,
        "_rpc_line_reader",
        lambda process: (_stall_read_line([None]), lambda: None),
    )

    result = run_pi_rpc_agent(
        replace(_config(tmp_path), stall_timeout_ms=100),
        _issue(),
        "prompt",
        plane_cli_source=helper,
        popen_factory=lambda *a, **k: process,
        mkdtemp=lambda **k: str(temp_dir),
        kill_process_group=lambda pid, sig: signals.append(sig),
        clock=_clock([0.0, 0.0, 0.0, 0.11, 0.12]),
        environ={"PATH": "/usr/bin"},
    )

    assert result.exit_code == -1
    assert result.timed_out is False
    assert result.stderr.startswith(STALL_WATCHDOG_SENTINEL + "\n")
    assert signals == [signal.SIGTERM]


def test_run_remote_agent_stall_returns_watchdog_sentinel(
    monkeypatch, tmp_path: Path
) -> None:
    process = FakeRpcProcess([])
    signals: list[int] = []
    config = replace(_config(tmp_path), stall_timeout_ms=100)
    binding = ProjectBinding(
        name="remote",
        plane_project_id="project",
        repo_path=tmp_path,
        base_branch="main",
        tracker_contract=config.bindings[0].tracker_contract,
        tracker="podium",
        remote=RemotePolicy(host="host", user="user"),
    )
    monkeypatch.setattr(
        agent_runner_module,
        "_rpc_line_reader",
        lambda process: (_stall_read_line([None]), lambda: None),
    )

    result = run_remote_agent(
        config,
        _issue(),
        "prompt",
        binding=binding,
        popen_factory=lambda *a, **k: process,
        kill_process_group=lambda pid, sig: signals.append(sig),
        clock=_clock([0.0, 0.0, 0.0, 0.11, 0.12]),
        environ={"PATH": "/usr/bin", "SYMPHONY_RUNTIME_DIR": str(tmp_path)},
    )

    assert result.exit_code == -1
    assert result.timed_out is False
    assert result.stderr.startswith(STALL_WATCHDOG_SENTINEL + "\n")
    assert signals == [signal.SIGTERM]


def test_run_pi_rpc_agent_timeout_sends_abort(tmp_path: Path) -> None:
    temp_dir = tmp_path / "temp-helper"
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    process = FakeRpcProcess([])
    signals: list[int] = []

    result = run_pi_rpc_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        plane_cli_source=helper,
        popen_factory=lambda *a, **k: process,
        mkdtemp=lambda **k: str(temp_dir),
        kill_process_group=lambda pid, sig: signals.append(sig),
        clock=_clock([0.0, 0.0, 2.0, 2.1]),
        environ={"PATH": "/usr/bin"},
    )

    assert result.timed_out is True
    assert result.exit_code == -1
    commands = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
    assert commands[-1] == {"type": "abort"}
    assert signals == [signal.SIGTERM]


def test_run_pi_rpc_agent_extracts_only_assistant_text_deltas(tmp_path: Path) -> None:
    """Real pi event shape: only `message_update` text_deltas are captured;
    thinking deltas, extension banners, and prompt echoes are excluded."""
    temp_dir = tmp_path / "temp-helper"
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    process = FakeRpcProcess(
        [
            json.dumps({"type": "agent_start"}) + "\n",
            json.dumps({"type": "response", "command": "prompt", "success": True})
            + "\n",
            json.dumps(
                {
                    "type": "extension_ui_request",
                    "method": "setStatus",
                    "statusText": "Advisor restored",
                }
            )
            + "\n",
            json.dumps(
                {
                    "type": "message_update",
                    "assistantMessageEvent": {
                        "type": "thinking_delta",
                        "delta": "pondering",
                    },
                }
            )
            + "\n",
            json.dumps(
                {
                    "type": "message_update",
                    "assistantMessageEvent": {
                        "type": "text_delta",
                        "delta": "SYMPHONY_RESULT: done\n",
                    },
                }
            )
            + "\n",
            json.dumps(
                {
                    "type": "message_update",
                    "assistantMessageEvent": {
                        "type": "text_delta",
                        "delta": "SYMPHONY_SUMMARY: ok",
                    },
                }
            )
            + "\n",
            json.dumps({"type": "agent_end", "exit_code": 0}) + "\n",
        ]
    )

    result = run_pi_rpc_agent(
        _config(tmp_path),
        _issue(),
        "rendered prompt",
        plane_cli_source=helper,
        popen_factory=lambda *a, **k: process,
        mkdtemp=lambda **k: str(temp_dir),
        kill_process_group=lambda pid, sig: None,
        clock=lambda: 0.0,
        environ={"PATH": "/usr/bin"},
    )

    assert result.exit_code == 0
    assert result.timed_out is False
    # only the two text_deltas — no banner, no thinking, no prompt echo
    assert result.stdout == "SYMPHONY_RESULT: done\nSYMPHONY_SUMMARY: ok"


def test_run_pi_rpc_agent_cleans_up_pidfile(tmp_path: Path) -> None:
    """A completed RPC run registers a pidfile under <runtime>/rpc and removes
    it on exit (so only a crash leaves an orphan for the boot sweep to reap)."""
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    process = FakeRpcProcess([json.dumps({"type": "agent_end", "exit_code": 0}) + "\n"])

    run_pi_rpc_agent(
        _config(tmp_path),
        _issue(),
        "rendered prompt",
        plane_cli_source=helper,
        popen_factory=lambda *a, **k: process,
        mkdtemp=lambda **k: str(tmp_path / "helper"),
        kill_process_group=lambda pid, sig: None,
        clock=lambda: 0.0,
        environ={"PATH": "/usr/bin", "SYMPHONY_RUNTIME_DIR": str(tmp_path)},
    )

    rpc_dir = tmp_path / "rpc"
    assert rpc_dir.exists()  # the registry dir was created during launch
    assert list(rpc_dir.glob("*.pid")) == []  # pidfile removed on clean exit


def test_run_pi_rpc_agent_cleans_up_steer_queue_on_completion(tmp_path: Path) -> None:
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    process = FakeRpcProcess([json.dumps({"type": "agent_end", "exit_code": 0}) + "\n"])
    environ = {"PATH": "/usr/bin", "SYMPHONY_RUNTIME_DIR": str(tmp_path)}
    steer_queue.write_steer_record("run-1", _issue().id, kind="abort", environ=environ)
    issue = CandidateIssue(
        id="issue-123",
        identifier="HOM-123",
        name="Test issue",
        description="Test description",
        labels=(),
        created_at="2026-05-04T00:00:00+00:00",
        active_run_id="run-1",
    )

    result = run_pi_rpc_agent(
        _config(tmp_path),
        issue,
        "rendered prompt",
        plane_cli_source=helper,
        popen_factory=lambda *a, **k: process,
        mkdtemp=lambda **k: str(tmp_path / "helper"),
        kill_process_group=lambda pid, sig: None,
        clock=lambda: 0.0,
        environ=environ,
    )

    assert result.exit_code == 0
    assert not steer_queue.steer_queue_path("run-1", environ).exists()


def test_run_pi_rpc_agent_cleans_up_steer_queue_on_timeout(tmp_path: Path) -> None:
    helper = tmp_path / "plane_cli.py"
    helper.write_text("print('helper')\n")
    process = FakeRpcProcess([])
    environ = {"PATH": "/usr/bin", "SYMPHONY_RUNTIME_DIR": str(tmp_path)}
    steer_queue.write_steer_record("run-2", _issue().id, kind="abort", environ=environ)
    issue = CandidateIssue(
        id="issue-123",
        identifier="HOM-123",
        name="Test issue",
        description="Test description",
        labels=(),
        created_at="2026-05-04T00:00:00+00:00",
        active_run_id="run-2",
    )

    result = run_pi_rpc_agent(
        _config(tmp_path),
        issue,
        "rendered prompt",
        plane_cli_source=helper,
        popen_factory=lambda *a, **k: process,
        mkdtemp=lambda **k: str(tmp_path / "helper"),
        kill_process_group=lambda pid, sig: None,
        clock=_clock([0.0, 0.0, 2.0, 2.1]),
        environ=environ,
    )

    assert result.timed_out is True
    assert not steer_queue.steer_queue_path("run-2", environ).exists()


def test_reap_orphan_rpc_processes_kills_alive_matching(tmp_path: Path) -> None:
    rpc_dir = tmp_path / "rpc"
    rpc_dir.mkdir()
    (rpc_dir / "111.pid").write_text("9999")  # recorded start-time
    (rpc_dir / "222.pid").write_text("8888")
    killed: list[tuple[int, int]] = []

    count = reap_orphan_rpc_processes(
        pidfile_dir=rpc_dir,
        is_alive=lambda pid: pid == 111,  # 222 already dead
        read_start_time=lambda pid: "9999" if pid == 111 else "0",
        kill_group=lambda pid, sig: killed.append((pid, sig)),
    )

    assert count == 1
    assert killed == [(111, signal.SIGKILL)]  # pi ignores SIGTERM
    assert list(rpc_dir.glob("*.pid")) == []  # both pidfiles cleaned up


def test_reap_orphan_rpc_processes_clears_stale_steer_queues(tmp_path: Path) -> None:
    environ = {"SYMPHONY_RUNTIME_DIR": str(tmp_path)}
    steer_queue.write_steer_record(
        "stale-run-1", _issue().id, kind="abort", environ=environ
    )
    steer_queue.write_steer_record(
        "stale-run-2", _issue().id, kind="steer", message="cancel", environ=environ
    )

    count = reap_orphan_rpc_processes(environ=environ, kill_group=lambda pid, sig: None)

    assert count == 0
    assert list(steer_queue.steer_queue_dir(environ).glob("*.jsonl")) == []


def test_reap_orphan_rpc_processes_skips_pid_reuse(tmp_path: Path) -> None:
    """An alive pid whose /proc start-time no longer matches the recorded value
    (pid reuse) must not be killed — only the stale pidfile is removed."""
    rpc_dir = tmp_path / "rpc"
    rpc_dir.mkdir()
    (rpc_dir / "333.pid").write_text("5555")  # recorded at launch
    killed: list[int] = []

    count = reap_orphan_rpc_processes(
        pidfile_dir=rpc_dir,
        is_alive=lambda pid: True,
        read_start_time=lambda pid: "7777",  # different process now holds the pid
        kill_group=lambda pid, sig: killed.append(pid),
    )

    assert count == 0
    assert killed == []
    assert list(rpc_dir.glob("*.pid")) == []


def test_reap_orphan_rpc_processes_skips_unverifiable(tmp_path: Path) -> None:
    """A pidfile with no recorded start-time can't be verified, so its process
    is not killed (only the file is cleaned up)."""
    rpc_dir = tmp_path / "rpc"
    rpc_dir.mkdir()
    (rpc_dir / "444.pid").write_text("")
    killed: list[int] = []

    count = reap_orphan_rpc_processes(
        pidfile_dir=rpc_dir,
        is_alive=lambda pid: True,
        read_start_time=lambda pid: "1234",
        kill_group=lambda pid, sig: killed.append(pid),
    )

    assert count == 0
    assert killed == []
    assert list(rpc_dir.glob("*.pid")) == []


def test_reap_orphan_rpc_processes_missing_dir(tmp_path: Path) -> None:
    assert reap_orphan_rpc_processes(pidfile_dir=tmp_path / "absent") == 0


def test_verify_pi_rpc_support_ok(tmp_path: Path) -> None:
    process = FakeRpcProcess(
        [
            json.dumps({"type": "agent_start"}) + "\n",
            json.dumps(
                {
                    "type": "response",
                    "command": "get_state",
                    "success": True,
                    "data": {},
                }
            )
            + "\n",
        ]
    )
    ok = verify_pi_rpc_support(
        "pi",
        tmp_path,
        popen_factory=lambda *a, **k: process,
        environ={"PATH": "/usr/bin"},
        clock=lambda: 0.0,
        kill_process_group=lambda pid, sig: None,
    )
    assert ok is True
    sent = json.loads(process.stdin.getvalue().splitlines()[0])
    assert sent == {"type": "get_state"}


def test_verify_pi_rpc_support_reports_failure(tmp_path: Path) -> None:
    process = FakeRpcProcess(
        [
            json.dumps(
                {
                    "type": "response",
                    "command": "get_state",
                    "success": False,
                    "error": "boom",
                }
            )
            + "\n",
        ]
    )
    ok = verify_pi_rpc_support(
        "pi",
        tmp_path,
        popen_factory=lambda *a, **k: process,
        environ={"PATH": "/usr/bin"},
        clock=lambda: 0.0,
        kill_process_group=lambda pid, sig: None,
    )
    assert ok is False


def test_verify_pi_rpc_support_stream_closed(tmp_path: Path) -> None:
    process = FakeRpcProcess([])  # no response before EOF
    ok = verify_pi_rpc_support(
        "pi",
        tmp_path,
        popen_factory=lambda *a, **k: process,
        environ={"PATH": "/usr/bin"},
        clock=lambda: 0.0,
        kill_process_group=lambda pid, sig: None,
    )
    assert ok is False


@pytest.mark.skipif(
    not os.environ.get("SYMPHONY_RPC_PARITY"),
    reason="real-pi parity check; set SYMPHONY_RPC_PARITY=1 to run (ADR-0010 Slice A)",
)
def test_run_pi_rpc_agent_real_pi_completion_parity(tmp_path: Path) -> None:
    """In-app Slice A gate: drive REAL `pi --mode rpc` to completion and confirm
    the adapter detects `agent_end` (not a timeout) and returns clean text.

    Opt-in only (hits a live provider/model). Run with:
        SYMPHONY_RPC_PARITY=1 uv run pytest tests/test_agent_runner.py -k real_pi -q
    """
    pi_bin = os.environ.get("PI_BIN", "/home/james/.npm-global/bin/pi")
    cfg = SymphonyConfig(
        plane_api_url="",
        plane_api_key="",
        plane_workspace_slug="",
        plane_project_id="",
        homelab_repo_path=tmp_path,
        pi_bin=pi_bin,
        pi_provider=os.environ.get("SYMPHONY_RPC_PARITY_PROVIDER", "openai-codex"),
        pi_model=os.environ.get("SYMPHONY_RPC_PARITY_MODEL", "gpt-5.4-mini"),
        run_timeout_ms=120_000,
    )
    result = run_pi_rpc_agent(
        cfg, _issue(), "Reply with exactly the token PARITY_OK and nothing else."
    )

    assert result.timed_out is False, (
        "adapter must detect agent_end, not hang to timeout"
    )
    assert result.exit_code == 0
    assert "PARITY_OK" in result.stdout
