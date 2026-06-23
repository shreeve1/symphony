"""ClaudeHost transports (ADR-0012 v2): LocalClaudeHost (Step A), SshClaudeHost (Step B)."""

import subprocess
from pathlib import Path

from claude_host import ClaudeHost, LocalClaudeHost, SshClaudeHost
from config import RemotePolicy


def test_write_then_read_roundtrips(tmp_path: Path) -> None:
    host = LocalClaudeHost()
    target = tmp_path / "prompt.txt"
    host.write_text(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"
    assert host.read_text(target) == "hello"


def test_read_text_missing_file_is_empty(tmp_path: Path) -> None:
    assert LocalClaudeHost().read_text(tmp_path / "absent.txt") == ""


def test_exists_tracks_the_filesystem(tmp_path: Path) -> None:
    host = LocalClaudeHost()
    target = tmp_path / "done.0"
    assert host.exists(target) is False
    host.write_text(target, "")
    assert host.exists(target) is True


def test_mkdtemp_uses_injected_func_and_prefix() -> None:
    calls: list[str] = []

    def fake_mkdtemp(*, prefix: str) -> str:
        calls.append(prefix)
        return "/tmp/fake-dir"

    result = LocalClaudeHost(fake_mkdtemp).mkdtemp(prefix="sym-")
    assert result == Path("/tmp/fake-dir")
    assert calls == ["sym-"]


def test_protocol_declares_complete_claude_host_seam() -> None:
    assert {"tmux_argv", "is_remote", "rmtree"} <= set(ClaudeHost.__dict__)


def test_local_host_tmux_argv_and_is_remote() -> None:
    host = LocalClaudeHost()
    assert host.tmux_argv(Path("/tmp/s.sock"), "new-session", "-d") == [
        "tmux",
        "-S",
        "/tmp/s.sock",
        "new-session",
        "-d",
    ]
    assert host.is_remote is False


def test_local_host_rmtree_ignores_missing_and_removes_tree_or_file(
    tmp_path: Path,
) -> None:
    target = tmp_path / "scratch"
    (target / "nested").mkdir(parents=True)
    (target / "nested" / "file.txt").write_text("x", encoding="utf-8")
    file_target = tmp_path / "socket.sock"
    file_target.write_text("x", encoding="utf-8")

    host = LocalClaudeHost()
    host.rmtree(target)
    host.rmtree(file_target)
    host.rmtree(target)
    host.rmtree(file_target)

    assert not target.exists()
    assert not file_target.exists()


# --- SshClaudeHost (Step B): remote transport over a pooled SSH ControlMaster ---

REMOTE = RemotePolicy(host="n8n", user="symphony", identity="/keys/id")


def _recorder(returncode: int = 0, stdout: str = "", stderr: str = ""):
    calls: list[dict] = []

    def run_func(argv, **kwargs):
        calls.append({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    return run_func, calls


def test_ssh_host_wraps_every_op_with_base_args_and_controlmaster() -> None:
    run_func, calls = _recorder(stdout="/tmp/remote-dir\n")
    host = SshClaudeHost(REMOTE, run_func=run_func, control_path=Path("/run/c.ctl"))

    host.mkdtemp(prefix="sym-")
    argv = calls[0]["argv"]
    # ssh base args (BatchMode/keepalive/identity) precede the host, then command.
    assert argv[0] == "ssh"
    assert "ControlMaster=auto" in argv
    assert "ControlPath=/run/c.ctl" in argv
    assert "-i" in argv and "/keys/id" in argv
    # host comes before the remote command; -o options come before the host.
    host_idx = argv.index("symphony@n8n")
    assert argv.index("ControlMaster=auto") < host_idx
    assert host_idx == len(argv) - 2  # remote command is the final element


def test_ssh_host_write_text_pipes_via_stdin_and_checks() -> None:
    run_func, calls = _recorder()
    host = SshClaudeHost(REMOTE, run_func=run_func)
    host.write_text(Path("/tmp/d/prompt.txt"), "hello")
    call = calls[0]
    assert call["input"] == "hello"
    assert call["check"] is True
    assert call["argv"][-1] == "cat > /tmp/d/prompt.txt"


def test_ssh_host_read_text_returns_stdout_on_success() -> None:
    run_func, _ = _recorder(returncode=0, stdout="payload")
    assert SshClaudeHost(REMOTE, run_func=run_func).read_text(Path("/x")) == "payload"


def test_ssh_host_read_text_empty_on_missing_or_timeout() -> None:
    run_func, _ = _recorder(returncode=1, stdout="ignored")
    assert SshClaudeHost(REMOTE, run_func=run_func).read_text(Path("/x")) == ""

    def boom(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 10)

    assert SshClaudeHost(REMOTE, run_func=boom).read_text(Path("/x")) == ""


def test_ssh_host_exists_tracks_returncode() -> None:
    run_ok, _ = _recorder(returncode=0)
    run_no, _ = _recorder(returncode=1)
    assert SshClaudeHost(REMOTE, run_func=run_ok).exists(Path("/done.0")) is True
    assert SshClaudeHost(REMOTE, run_func=run_no).exists(Path("/done.0")) is False


def test_ssh_host_mkdtemp_returns_remote_path() -> None:
    run_func, calls = _recorder(stdout="/tmp/sym-abc123\n")
    result = SshClaudeHost(REMOTE, run_func=run_func).mkdtemp(prefix="sym-")
    assert result == Path("/tmp/sym-abc123")
    assert calls[0]["argv"][-1] == "mktemp -d /tmp/sym-XXXXXXXX"


def test_ssh_host_tmux_argv_runs_tmux_on_remote() -> None:
    host = SshClaudeHost(REMOTE, run_func=_recorder()[0])
    argv = host.tmux_argv(Path("/tmp/s.sock"), "capture-pane", "-pt", "sess")
    assert host.is_remote is True
    assert argv[0] == "ssh" and "symphony@n8n" in argv
    tail = argv[argv.index("symphony@n8n") + 1 :]
    assert tail == ["tmux", "-S", "/tmp/s.sock", "capture-pane", "-pt", "sess"]


def test_ssh_host_rmtree_runs_remote_rm_rf() -> None:
    run_func, calls = _recorder()
    SshClaudeHost(REMOTE, run_func=run_func).rmtree(Path("/tmp/has space"))
    call = calls[0]
    assert call["check"] is False
    assert call["argv"][-1] == "rm -rf '/tmp/has space'"
