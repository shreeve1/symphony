from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_runner import (
    AgentResult,
    AgentRunnerError,
    RemoteAgentAdapter,
    RoutingAgentAdapter,
    _build_remote_command,
    _remote_callback_port,
    run_remote_agent,
)
from config import ProjectBinding, RemotePolicy, SymphonyConfig
from plane_poller import CandidateIssue
from tracker_contract import DEFAULT_CONTRACT


class Completed:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class FakeProcess:
    def __init__(self, responses: list[object] | None = None, returncode: int = 0):
        self.pid = 4242
        self.returncode = returncode
        self.responses = responses or [("agent output", "")]

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response  # type: ignore[return-value]


def _config(tmp_path: Path) -> SymphonyConfig:
    return SymphonyConfig(
        plane_api_url="http://127.0.0.1:8000",
        plane_api_key="fake-plane-key-for-tests",
        plane_workspace_slug="homelab",
        plane_project_id="fake-project-id",
        homelab_repo_path=tmp_path,
        pi_bin="/home/james/.npm-global/bin/pi",
        pi_provider="zai",
        pi_model="glm-5.1:high",
        run_timeout_ms=1000,
    )


def _remote_binding(repo: str = "/home/itadmin/symphony") -> ProjectBinding:
    return ProjectBinding(
        name="n8n",
        plane_project_id="n8n",
        repo_path=Path(repo),
        base_branch="main",
        tracker_contract=DEFAULT_CONTRACT,
        tracker="podium",
        remote=RemotePolicy(host="100.95.224.218", user="itadmin"),
    )


def _issue() -> CandidateIssue:
    return CandidateIssue(
        id="issue-27",
        identifier="N8N-27",
        name="Test issue",
        description="Test description",
        labels=(),
        created_at="2026-06-16T00:00:00+00:00",
    )


def test_remote_callback_port_parses_and_defaults() -> None:
    assert _remote_callback_port("http://127.0.0.1:8000") == 8000
    assert _remote_callback_port("http://127.0.0.1:8000/") == 8000
    assert _remote_callback_port("http://localhost") == 8000


def test_build_remote_command_quotes_and_orders() -> None:
    cmd = _build_remote_command(
        repo_path="/home/itadmin/sym phony",
        exports={"SYMPHONY_PLANE_API_URL": "http://127.0.0.1:8000"},
        pi_command=["pi", "--print", "a prompt; rm -rf /"],
        helper_dir="/tmp/symphony-remote-issue-27",
    )
    assert cmd.startswith("cd '/home/itadmin/sym phony' &&")
    assert "export SYMPHONY_PLANE_API_URL=http://127.0.0.1:8000;" in cmd
    assert "PATH=/tmp/symphony-remote-issue-27:$PATH" in cmd
    # The malicious prompt is quoted, not interpreted.
    assert "'a prompt; rm -rf /'" in cmd


def test_run_remote_agent_ships_helper_and_builds_ssh(tmp_path: Path) -> None:
    run_calls: list[tuple[list[str], dict]] = []
    popen_calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        run_calls.append((command, kwargs))
        return Completed(returncode=0)

    def fake_popen(command, **kwargs):
        popen_calls.append((command, kwargs))
        return FakeProcess(responses=[("done", "")])

    result = run_remote_agent(
        _config(tmp_path),
        _issue(),
        "do the work",
        binding=_remote_binding(),
        run_func=fake_run,
        popen_factory=fake_popen,
    )

    assert result == AgentResult(0, result.duration_ms, False, "done", "")

    # First run_func call ships the helper to the remote temp dir over SSH.
    ship_cmd, ship_kwargs = run_calls[0]
    assert ship_cmd[0] == "ssh"
    assert "itadmin@100.95.224.218" in ship_cmd
    assert "BatchMode=yes" in ship_cmd
    assert "cat > /tmp/symphony-remote-issue-27/plane" in ship_cmd[-1]
    assert ship_kwargs["input"]  # helper text piped on stdin

    # The exec call carries the reverse tunnel and the remote command.
    exec_cmd, _ = popen_calls[0]
    assert exec_cmd[0] == "ssh"
    assert "-R" in exec_cmd
    assert "8000:127.0.0.1:8000" in exec_cmd
    assert exec_cmd[-2] == "itadmin@100.95.224.218"
    remote_command = exec_cmd[-1]
    assert remote_command.startswith("cd /home/itadmin/symphony &&")
    assert "export SYMPHONY_PLANE_API_URL=http://127.0.0.1:8000;" in remote_command
    assert "export SYMPHONY_ISSUE_ID=issue-27;" in remote_command
    # pi dispatched by basename so the remote PATH resolves it.
    assert " pi --print --no-session" in remote_command
    assert "'do the work'" in remote_command

    # Last run_func call is best-effort remote cleanup.
    cleanup_cmd, _ = run_calls[-1]
    assert "rm -rf /tmp/symphony-remote-issue-27" in cleanup_cmd[-1]


def test_run_remote_agent_identity_flag(tmp_path: Path) -> None:
    binding = ProjectBinding(
        name="n8n",
        plane_project_id="n8n",
        repo_path=Path("/home/itadmin/symphony"),
        base_branch="main",
        tracker_contract=DEFAULT_CONTRACT,
        tracker="podium",
        remote=RemotePolicy(host="h", user="u", identity="/keys/id_ed25519"),
    )
    popen_calls: list[list[str]] = []

    run_remote_agent(
        _config(tmp_path),
        _issue(),
        "go",
        binding=binding,
        run_func=lambda *a, **k: Completed(returncode=0),
        popen_factory=lambda c, **k: popen_calls.append(c) or FakeProcess([("x", "")]),
    )

    exec_cmd = popen_calls[0]
    assert "-i" in exec_cmd
    assert "/keys/id_ed25519" in exec_cmd


def test_run_remote_agent_silent_exit_is_failure(tmp_path: Path) -> None:
    result = run_remote_agent(
        _config(tmp_path),
        _issue(),
        "go",
        binding=_remote_binding(),
        run_func=lambda *a, **k: Completed(returncode=0),
        popen_factory=lambda *a, **k: FakeProcess([("", "")]),
    )
    assert result.exit_code == 137
    assert "empty stdout/stderr" in result.stderr


def test_run_remote_agent_timeout_terminates(tmp_path: Path) -> None:
    kills: list[tuple[int, int]] = []
    proc = FakeProcess(
        responses=[
            subprocess.TimeoutExpired(cmd="ssh", timeout=1.0),
            ("partial", "terminated"),
        ]
    )

    result = run_remote_agent(
        _config(tmp_path),
        _issue(),
        "go",
        binding=_remote_binding(),
        run_func=lambda *a, **k: Completed(returncode=0),
        popen_factory=lambda *a, **k: proc,
        kill_process_group=lambda pid, sig: kills.append((pid, sig)),
    )

    assert result.timed_out is True
    assert result.exit_code == -1
    assert kills and kills[0][0] == proc.pid


def test_run_remote_agent_ship_failure_raises(tmp_path: Path) -> None:
    with pytest.raises(AgentRunnerError, match="ship plane helper"):
        run_remote_agent(
            _config(tmp_path),
            _issue(),
            "go",
            binding=_remote_binding(),
            run_func=lambda *a, **k: Completed(stderr="permission denied", returncode=255),
            popen_factory=lambda *a, **k: FakeProcess(),
        )


def test_run_remote_agent_rejects_non_remote_binding(tmp_path: Path) -> None:
    local = ProjectBinding(
        name="local",
        plane_project_id="p",
        repo_path=tmp_path,
        base_branch="main",
        tracker_contract=DEFAULT_CONTRACT,
    )
    with pytest.raises(AgentRunnerError, match="non-remote binding"):
        run_remote_agent(_config(tmp_path), _issue(), "go", binding=local)


def test_remote_adapter_delegates(tmp_path: Path, monkeypatch) -> None:
    import agent_runner

    seen: dict[str, object] = {}

    def fake_run_remote_agent(config, issue, prompt, *, binding):
        seen["binding"] = binding
        seen["prompt"] = prompt
        return AgentResult(0, 1, False, "delegated", "")

    monkeypatch.setattr(agent_runner, "run_remote_agent", fake_run_remote_agent)
    binding = _remote_binding()
    adapter = RemoteAgentAdapter(config=_config(tmp_path), binding=binding)
    result = adapter(_issue(), "go")
    assert result.stdout == "delegated"
    assert seen["binding"] is binding
    assert seen["prompt"] == "go"


def test_routing_remote_pi_uses_remote_adapter() -> None:
    calls: list[str] = []

    def remote(issue, prompt, /):
        calls.append("remote")
        return AgentResult(0, 1, False, "ok", "")

    def local(issue, prompt, /):
        calls.append("local")
        return AgentResult(0, 1, False, "local", "")

    router = RoutingAgentAdapter(
        binding=_remote_binding(),
        pi_adapter=local,
        claude_adapter=local,
        remote_adapter=remote,
    )
    result = router(_issue(), "go")
    assert result.stdout == "ok"
    assert calls == ["remote"]


def test_routing_remote_claude_rejected() -> None:
    binding = ProjectBinding(
        name="n8n",
        plane_project_id="n8n",
        repo_path=Path("/home/itadmin/symphony"),
        base_branch="main",
        tracker_contract=DEFAULT_CONTRACT,
        tracker="podium",
        default_agent="claude",
        remote=RemotePolicy(host="h", user="u"),
    )
    router = RoutingAgentAdapter(
        binding=binding,
        pi_adapter=lambda i, p: AgentResult(0, 1, False),
        claude_adapter=lambda i, p: AgentResult(0, 1, False),
        remote_adapter=lambda i, p: AgentResult(0, 1, False),
    )
    with pytest.raises(AgentRunnerError, match="only pi dispatch"):
        router(_issue(), "go")


def test_routing_remote_without_adapter_raises() -> None:
    router = RoutingAgentAdapter(
        binding=_remote_binding(),
        pi_adapter=lambda i, p: AgentResult(0, 1, False),
        claude_adapter=lambda i, p: AgentResult(0, 1, False),
        remote_adapter=None,
    )
    with pytest.raises(AgentRunnerError, match="no remote adapter"):
        router(_issue(), "go")
