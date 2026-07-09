from __future__ import annotations

import io
import json
import signal
import subprocess
from dataclasses import replace
from importlib import import_module
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

steer_queue = import_module("web.api.steer_queue")


class Completed:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class FakeRpcProcess:
    def __init__(self, lines: list[str] | None = None, returncode: int | None = 0):
        self.pid = 4242
        self.returncode = returncode
        self.stdin = io.StringIO()
        if lines is None:
            lines = [json.dumps({"type": "agent_end", "exit_code": returncode}) + "\n"]
        self.stdout = io.StringIO("".join(lines))
        self.stderr = io.StringIO("")
        self.wait_calls: list[float | None] = []
        self.communicate_calls: list[float | None] = []

    def poll(self) -> int | None:
        if self.stdout.tell() == len(self.stdout.getvalue()):
            return self.returncode
        return None

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        return self.returncode or 0

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        self.communicate_calls.append(timeout)
        return self.stdout.read(), self.stderr.read()


def _rpc_done(text: str, *, exit_code: int = 0) -> list[str]:
    return [
        json.dumps({"type": "message_update", "delta": text}) + "\n",
        json.dumps({"type": "agent_end", "exit_code": exit_code}) + "\n",
    ]


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


def _remote_binding(
    repo: str = "/home/itadmin/symphony", *, tracker: str = "podium"
) -> ProjectBinding:
    return ProjectBinding(
        name="n8n",
        plane_project_id="n8n",
        repo_path=Path(repo),
        base_branch="main",
        tracker_contract=DEFAULT_CONTRACT,
        tracker="plane" if tracker == "plane" else "podium",
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


def test_run_remote_agent_gated_forwards_podium_tunnel_and_env(
    tmp_path: Path,
) -> None:
    popen_calls: list[list[str]] = []
    issue = replace(
        _issue(), preferred_skill="podium-issues-remote", binding_name="n8n"
    )

    run_remote_agent(
        _config(tmp_path),
        issue,
        "spec",
        binding=_remote_binding(),
        run_func=lambda *a, **k: Completed(returncode=0),
        popen_factory=lambda c, **k: (
            popen_calls.append(c) or FakeRpcProcess(_rpc_done("done"))
        ),
        environ={"PODIUM_API_TOKEN": "test-token"},
    )

    exec_cmd = popen_calls[0]
    assert "-R" in exec_cmd
    assert "8090:127.0.0.1:8090" in exec_cmd
    remote_command = exec_cmd[-1]
    assert "export PODIUM_BASE_URL=http://127.0.0.1:8090;" in remote_command
    assert "export PODIUM_API_TOKEN=test-token;" in remote_command
    assert "export SYMPHONY_BINDING_NAME=n8n;" in remote_command


def test_run_remote_agent_non_gated_podium_binding_unchanged(tmp_path: Path) -> None:
    popen_calls: list[list[str]] = []

    run_remote_agent(
        _config(tmp_path),
        _issue(),
        "do the work",
        binding=_remote_binding(),
        run_func=lambda *a, **k: Completed(returncode=0),
        popen_factory=lambda c, **k: (
            popen_calls.append(c) or FakeRpcProcess(_rpc_done("done"))
        ),
        environ={"PODIUM_API_TOKEN": "test-token"},
    )

    exec_cmd = popen_calls[0]
    assert "8000:127.0.0.1:8000" in exec_cmd
    remote_command = exec_cmd[-1]
    assert "PODIUM_BASE_URL" not in remote_command
    assert "PODIUM_API_TOKEN" not in remote_command
    assert "SYMPHONY_BINDING_NAME" not in remote_command


def test_run_remote_agent_gated_without_token_raises(tmp_path: Path) -> None:
    issue = replace(_issue(), preferred_skill="podium-issues-remote")
    with pytest.raises(AgentRunnerError, match="PODIUM_API_TOKEN not set"):
        run_remote_agent(
            _config(tmp_path),
            issue,
            "spec",
            binding=_remote_binding(),
            run_func=lambda *a, **k: Completed(returncode=0),
            popen_factory=lambda c, **k: FakeRpcProcess(_rpc_done("done")),
            environ={},
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


def test_run_remote_agent_creates_remote_worktree_when_active(tmp_path: Path) -> None:
    run_calls: list[tuple[list[str], dict]] = []
    popen_calls: list[tuple[list[str], dict]] = []
    issue = replace(
        _issue(), worktree_active=True, binding_name="n8n", base_branch="main"
    )

    def fake_run(command, **kwargs):
        run_calls.append((command, kwargs))
        return Completed(returncode=0)

    def fake_popen(command, **kwargs):
        popen_calls.append((command, kwargs))
        return FakeRpcProcess(_rpc_done("done"))

    result = run_remote_agent(
        _config(tmp_path),
        issue,
        "do the work",
        binding=_remote_binding(),
        run_func=fake_run,
        popen_factory=fake_popen,
    )

    assert result.exit_code == 0
    assert "worktree add" in run_calls[0][0][-1]
    remote_command = popen_calls[0][0][-1]
    assert remote_command.startswith(
        "cd /home/itadmin/symphony/worktrees/n8n/issue-27 &&"
    )


def test_run_remote_agent_omits_plane_env_and_helper_for_podium(tmp_path: Path) -> None:
    run_calls: list[tuple[list[str], dict]] = []
    popen_calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        run_calls.append((command, kwargs))
        return Completed(returncode=0)

    process = FakeRpcProcess(_rpc_done("done"))

    def fake_popen(command, **kwargs):
        popen_calls.append((command, kwargs))
        return process

    result = run_remote_agent(
        _config(tmp_path),
        _issue(),
        "do the work",
        binding=_remote_binding(),
        run_func=fake_run,
        popen_factory=fake_popen,
    )

    assert result == AgentResult(0, result.duration_ms, False, "done", "")

    assert run_calls == []

    # The exec call carries the reverse tunnel and the remote command.
    exec_cmd, _ = popen_calls[0]
    assert exec_cmd[0] == "ssh"
    assert "-R" in exec_cmd
    assert "8000:127.0.0.1:8000" in exec_cmd
    assert exec_cmd[-2] == "itadmin@100.95.224.218"
    remote_command = exec_cmd[-1]
    assert remote_command.startswith("cd /home/itadmin/symphony &&")
    assert "export SYMPHONY_ISSUE_ID=issue-27;" in remote_command
    assert "SYMPHONY_TRACKER_API_KEY" not in remote_command
    assert "SYMPHONY_TRACKER_API_URL" not in remote_command
    assert "SYMPHONY_TRACKER_FRONTEND_URL" not in remote_command
    assert "SYMPHONY_TRACKER_DASHBOARD_URL" not in remote_command
    assert "SYMPHONY_TRACKER_PROJECT_ID" not in remote_command
    assert "SYMPHONY_TRACKER_WORKSPACE_SLUG" not in remote_command
    assert "SYMPHONY_PLANE_API_KEY" not in remote_command
    assert "SYMPHONY_PLANE_API_URL" not in remote_command
    assert "SYMPHONY_PLANE_FRONTEND_URL" not in remote_command
    assert "SYMPHONY_PLANE_PROJECT_ID" not in remote_command
    assert "SYMPHONY_PLANE_WORKSPACE_SLUG" not in remote_command
    assert "PLANE_DASHBOARD_URL" not in remote_command
    assert "PATH=/tmp/symphony-remote-issue-27:$PATH" not in remote_command
    # pi dispatched by basename so the remote PATH resolves it, using RPC parity.
    assert " pi --mode rpc" in remote_command
    assert "--session-id" in remote_command
    assert "do the work" not in remote_command
    assert popen_calls[0][1]["stdin"] is subprocess.PIPE
    assert json.loads(process.stdin.getvalue().splitlines()[0]) == {
        "type": "prompt",
        "message": "do the work",
    }


def test_run_remote_agent_ships_helper_and_plane_env_for_plane_binding(
    tmp_path: Path,
) -> None:
    run_calls: list[tuple[list[str], dict]] = []
    popen_calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        run_calls.append((command, kwargs))
        return Completed(returncode=0)

    def fake_popen(command, **kwargs):
        popen_calls.append((command, kwargs))
        return FakeRpcProcess(_rpc_done("done"))

    run_remote_agent(
        _config(tmp_path),
        _issue(),
        "do the work",
        binding=_remote_binding(tracker="plane"),
        run_func=fake_run,
        popen_factory=fake_popen,
    )

    ship_cmd, ship_kwargs = run_calls[0]
    assert ship_cmd[0] == "ssh"
    assert "itadmin@100.95.224.218" in ship_cmd
    assert "BatchMode=yes" in ship_cmd
    assert "cat > /tmp/symphony-remote-issue-27/plane" in ship_cmd[-1]
    assert ship_kwargs["input"]

    remote_command = popen_calls[0][0][-1]
    assert "export SYMPHONY_TRACKER_API_URL=http://127.0.0.1:8000;" in remote_command
    assert "export SYMPHONY_TRACKER_API_KEY=fake-plane-key-for-tests;" in remote_command
    assert "export SYMPHONY_TRACKER_PROJECT_ID=fake-project-id;" in remote_command
    assert "export SYMPHONY_TRACKER_WORKSPACE_SLUG=homelab;" in remote_command
    assert "export SYMPHONY_PLANE_API_URL=http://127.0.0.1:8000;" in remote_command
    assert "export SYMPHONY_PLANE_API_KEY=fake-plane-key-for-tests;" in remote_command
    assert "PATH=/tmp/symphony-remote-issue-27:$PATH" in remote_command
    assert " pi --mode rpc" in remote_command

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
        popen_factory=lambda c, **k: (
            popen_calls.append(c) or FakeRpcProcess(_rpc_done("x"))
        ),
    )

    exec_cmd = popen_calls[0]
    assert "-i" in exec_cmd
    assert "/keys/id_ed25519" in exec_cmd


def test_run_remote_agent_ships_skill_and_uses_remote_skill_path(
    tmp_path: Path,
) -> None:
    skill_file = tmp_path / "skills" / "foo" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("---\nname: foo\n---\n", encoding="utf-8")
    (skill_file.parent / "asset.txt").write_text("asset\n", encoding="utf-8")
    issue = replace(_issue(), skill_source=str(skill_file))
    run_calls: list[tuple[list[str], dict]] = []
    popen_calls: list[list[str]] = []

    run_remote_agent(
        _config(tmp_path),
        issue,
        "go",
        binding=_remote_binding(),
        run_func=lambda c, **k: run_calls.append((c, k)) or Completed(returncode=0),
        popen_factory=lambda c, **k: (
            popen_calls.append(c) or FakeRpcProcess(_rpc_done("x"))
        ),
    )

    ship_cmd, ship_kwargs = run_calls[0]
    assert "tar -C /tmp/symphony-remote-issue-27/skill -xf -" in ship_cmd[-1]
    assert isinstance(ship_kwargs["input"], bytes)
    remote_command = popen_calls[0][-1]
    assert "--skill /tmp/symphony-remote-issue-27/skill" in remote_command
    cleanup_cmd, _ = run_calls[-1]
    assert "rm -rf /tmp/symphony-remote-issue-27" in cleanup_cmd[-1]


def test_run_remote_agent_forwards_queued_steer(tmp_path: Path) -> None:
    process = FakeRpcProcess(_rpc_done("ok"))
    environ = {"PATH": "/usr/bin", "SYMPHONY_RUNTIME_DIR": str(tmp_path)}
    steer_queue.write_steer_record(
        "run-remote-1",
        _issue().id,
        kind="steer",
        message="tighten scope",
        environ=environ,
    )
    issue = replace(_issue(), active_run_id="run-remote-1")

    result = run_remote_agent(
        _config(tmp_path),
        issue,
        "prompt",
        binding=_remote_binding(),
        run_func=lambda *a, **k: Completed(returncode=0),
        popen_factory=lambda *a, **k: process,
        kill_process_group=lambda pid, sig: None,
        clock=lambda: 0.0,
        environ=environ,
    )

    assert result.exit_code == 0
    commands = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
    assert commands[0] == {"type": "prompt", "message": "prompt"}
    assert {"type": "steer", "message": "tighten scope"} in commands


def test_run_remote_agent_forwards_queued_abort(tmp_path: Path) -> None:
    process = FakeRpcProcess(_rpc_done("ok"))
    environ = {"PATH": "/usr/bin", "SYMPHONY_RUNTIME_DIR": str(tmp_path)}
    steer_queue.write_steer_record(
        "run-remote-2", _issue().id, kind="abort", environ=environ
    )
    issue = replace(_issue(), active_run_id="run-remote-2")

    run_remote_agent(
        _config(tmp_path),
        issue,
        "prompt",
        binding=_remote_binding(),
        run_func=lambda *a, **k: Completed(returncode=0),
        popen_factory=lambda *a, **k: process,
        kill_process_group=lambda pid, sig: None,
        clock=lambda: 0.0,
        environ=environ,
    )

    commands = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
    assert {"type": "abort"} in commands


def test_run_remote_agent_silent_exit_is_failure(tmp_path: Path) -> None:
    # SSH closed before any agent_end event and before the local handle saw an
    # exit code (poll() -> None): drain.event_exit_code stays None, so the empty
    # exit is treated as a failure (137).
    result = run_remote_agent(
        _config(tmp_path),
        _issue(),
        "go",
        binding=_remote_binding(),
        run_func=lambda *a, **k: Completed(returncode=0),
        popen_factory=lambda *a, **k: FakeRpcProcess([], returncode=None),
    )
    assert result.exit_code == 137
    assert "empty stdout/stderr" in result.stderr


def test_run_remote_agent_clean_empty_exit_is_not_failure(tmp_path: Path) -> None:
    # Stream closed with the process reporting a clean exit code (poll() -> 0):
    # drain.event_exit_code is 0, so the empty exit is NOT a silent failure.
    result = run_remote_agent(
        _config(tmp_path),
        _issue(),
        "go",
        binding=_remote_binding(),
        run_func=lambda *a, **k: Completed(returncode=0),
        popen_factory=lambda *a, **k: FakeRpcProcess([], returncode=0),
    )
    assert result.exit_code == 0
    assert result.timed_out is False


def test_run_remote_agent_timeout_terminates(tmp_path: Path) -> None:
    kills: list[tuple[int, int]] = []
    proc = FakeRpcProcess([])

    result = run_remote_agent(
        _config(tmp_path),
        _issue(),
        "go",
        binding=_remote_binding(),
        run_func=lambda *a, **k: Completed(returncode=0),
        popen_factory=lambda *a, **k: proc,
        kill_process_group=lambda pid, sig: kills.append((pid, sig)),
        clock=iter([0.0, 0.0, 2.0, 2.1]).__next__,
    )

    assert result.timed_out is True
    assert result.exit_code == -1
    assert kills == [(proc.pid, signal.SIGTERM)]


def test_run_remote_agent_ship_failure_raises(tmp_path: Path) -> None:
    with pytest.raises(AgentRunnerError, match="ship plane helper"):
        run_remote_agent(
            _config(tmp_path),
            _issue(),
            "go",
            binding=_remote_binding(tracker="plane"),
            run_func=lambda *a, **k: Completed(
                stderr="permission denied", returncode=255
            ),
            popen_factory=lambda *a, **k: FakeRpcProcess(),
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


def test_routing_remote_claude_uses_claude_adapter() -> None:
    calls: list[str] = []
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
        claude_adapter=lambda i, p: calls.append("claude") or AgentResult(0, 1, False),
        remote_adapter=lambda i, p: calls.append("remote") or AgentResult(0, 1, False),
    )

    router(_issue(), "go")

    assert calls == ["claude"]


def test_routing_remote_without_adapter_raises() -> None:
    router = RoutingAgentAdapter(
        binding=_remote_binding(),
        pi_adapter=lambda i, p: AgentResult(0, 1, False),
        claude_adapter=lambda i, p: AgentResult(0, 1, False),
        remote_adapter=None,
    )
    with pytest.raises(AgentRunnerError, match="no remote adapter"):
        router(_issue(), "go")
