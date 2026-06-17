from __future__ import annotations

import json
import os
from itertools import chain, repeat
from pathlib import Path

from config import SymphonyConfig
from plane_poller import CandidateIssue

import claude_runner
from claude_runner import (
    ClaudeRunCleanup,
    issue_id_from_persistent_socket,
    persistent_socket_path,
    run_claude_agent,
)


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
        "created_at": "2026-06-17T00:00:00+00:00",
        "resolved_model": "claude-opus-4-8",
        "binding_name": "homelab",
    }
    values.update(kwargs)
    return CandidateIssue(**values)


def _path_after(text: str, marker: str) -> Path:
    return Path(text.split(marker, 1)[1].strip().splitlines()[0])


class PersistSuccessTmux:
    def __init__(self, result_text: str | None = "SYMPHONY_RESULT: done"):
        self.calls: list[list[str]] = []
        self.result_text = result_text
        self.result_file: Path | None = None
        self.done_file: Path | None = None
        self.socket_path: Path | None = None

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if command[:1] != ["tmux"]:
            return Completed()
        if "new-session" in command:
            self.socket_path = Path(command[2])
            self.socket_path.write_text("", encoding="utf-8")
            return Completed()
        if "display-message" in command:
            return Completed(stdout="")
        if "capture-pane" in command:
            return Completed(stdout="bypass permissions on")
        if "load-buffer" in command:
            prompt = Path(command[-1]).read_text(encoding="utf-8")
            self.result_file = _path_after(prompt, "literal result file path:")
            self.done_file = _path_after(prompt, "literal done file path:")
            return Completed()
        if "send-keys" in command:
            if self.result_text is not None:
                assert self.result_file is not None
                assert self.done_file is not None
                self.result_file.write_text(self.result_text, encoding="utf-8")
                self.done_file.write_text("", encoding="utf-8")
            return Completed()
        if "has-session" in command:
            return Completed(returncode=0)
        return Completed()


class ReattachSuccessTmux(PersistSuccessTmux):
    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if command[:1] != ["tmux"]:
            return Completed()
        if "display-message" in command:
            return Completed(stdout=f"{os.getpid()}\n")
        if "capture-pane" in command:
            return Completed(stdout="bypass permissions on")
        if "load-buffer" in command:
            prompt = Path(command[-1]).read_text(encoding="utf-8")
            self.result_file = _path_after(prompt, "literal result file path:")
            self.done_file = _path_after(prompt, "literal done file path:")
            return Completed()
        if "send-keys" in command:
            assert self.result_file is not None
            assert self.done_file is not None
            self.result_file.write_text("SYMPHONY_RESULT: done", encoding="utf-8")
            self.done_file.write_text("", encoding="utf-8")
            return Completed()
        if "has-session" in command:
            return Completed(returncode=0)
        return Completed()


class DeadSocketFallbackTmux(PersistSuccessTmux):
    def __init__(self):
        super().__init__()
        self.launched = False

    def __call__(self, command, **kwargs):
        if command[:1] == ["tmux"] and "has-session" in command:
            self.calls.append(command)
            return Completed(returncode=0 if self.launched else 1)
        if command[:1] == ["tmux"] and "new-session" in command:
            self.launched = True
        return super().__call__(command, **kwargs)


def test_persistent_socket_path_is_deterministic_sanitized_and_round_trips() -> None:
    first = persistent_socket_path("home lab", "42")
    second = persistent_socket_path("home lab", "42")

    assert first == second
    assert first == Path("/tmp/symphony-claude-persist-home-lab-42.sock")
    assert issue_id_from_persistent_socket(first) == "42"
    assert issue_id_from_persistent_socket("/tmp/symphony-claude-42-abc.sock") is None


def test_live_persistent_socket_reattaches_without_cold_start(
    tmp_path: Path, monkeypatch
) -> None:
    fake = ReattachSuccessTmux()
    pid_dir = tmp_path / "runtime" / "claude"
    session_file = tmp_path / "session.jsonl"
    expected_socket = persistent_socket_path("homelab", "42")
    expected_socket.write_text("", encoding="utf-8")
    monkeypatch.setattr(claude_runner, "pid_start_time", lambda pid: "12345")
    try:
        result = run_claude_agent(
            _config(tmp_path),
            _issue(),
            "prompt",
            run_func=fake,
            mkdtemp=lambda **_: str(tmp_path / "run"),
            nonce_factory=lambda: "nonce",
            clock=lambda: 0.0,
            sleep=lambda _: None,
            pidfile_dir=pid_dir,
            session_file=session_file,
            persist=True,
        )

        assert result.exit_code == 0
        assert not any("new-session" in command for command in fake.calls)
        load_index = next(
            i for i, command in enumerate(fake.calls) if "load-buffer" in command
        )
        capture_index = next(
            i for i, command in enumerate(fake.calls) if "capture-pane" in command
        )
        assert capture_index > load_index
        assert (pid_dir / f"{expected_socket.stem}.pid").read_text(
            encoding="utf-8"
        ) == f"{os.getpid()} 12345"
        metadata = json.loads(
            (pid_dir / f"{expected_socket.stem}.meta.json").read_text(encoding="utf-8")
        )
        assert metadata["issue_id"] == "42"
        assert metadata["binding"] == "homelab"
        assert metadata["session_file"] == str(session_file)
    finally:
        expected_socket.unlink(missing_ok=True)


def test_dead_persistent_socket_falls_back_to_cold_resume(tmp_path: Path) -> None:
    fake = DeadSocketFallbackTmux()
    pid_dir = tmp_path / "runtime" / "claude"
    session_file = tmp_path / "session.jsonl"
    session_file.write_text("{}\n", encoding="utf-8")
    expected_socket = persistent_socket_path("homelab", "42")
    expected_socket.write_text("stale", encoding="utf-8")
    try:
        result = run_claude_agent(
            _config(tmp_path),
            _issue(),
            "prompt",
            run_func=fake,
            mkdtemp=lambda **_: str(tmp_path / "run"),
            nonce_factory=lambda: "nonce",
            clock=lambda: 0.0,
            sleep=lambda _: None,
            pidfile_dir=pid_dir,
            session_file=session_file,
            persist=True,
        )

        assert result.exit_code == 0
        launch = next(command for command in fake.calls if "new-session" in command)
        assert "--resume" in launch
        assert any("kill-session" in command for command in fake.calls)
    finally:
        expected_socket.unlink(missing_ok=True)


def test_persist_false_still_uses_run_scoped_nonce_socket(tmp_path: Path) -> None:
    fake = PersistSuccessTmux()

    result = run_claude_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        nonce_factory=lambda: "abc",
        clock=lambda: 0.0,
        sleep=lambda _: None,
        persist=False,
    )

    assert result.exit_code == 0
    launch = next(command for command in fake.calls if "new-session" in command)
    assert str(launch[2]) == "/tmp/symphony-claude-42-abc.sock"
    assert any("kill-session" in command for command in fake.calls)


def test_cleanup_run_and_session_are_split_and_idempotent(tmp_path: Path) -> None:
    temp_dir = tmp_path / "run"
    temp_dir.mkdir()
    socket = tmp_path / "symphony-claude-persist-homelab-42.sock"
    socket.write_text("", encoding="utf-8")
    pidfile = tmp_path / "symphony-claude-persist-homelab-42.pid"
    pidfile.write_text("4242 99", encoding="utf-8")
    metadata = tmp_path / "symphony-claude-persist-homelab-42.meta.json"
    metadata.write_text("{}", encoding="utf-8")
    calls: list[list[str]] = []

    cleanup = ClaudeRunCleanup(
        socket,
        socket.stem,
        temp_dir,
        run_func=lambda command, **kwargs: calls.append(command) or Completed(),
        pidfile_path=pidfile,
        metadata_path=metadata,
    )

    cleanup.cleanup_run()
    cleanup.cleanup_run()
    assert not temp_dir.exists()
    assert socket.exists()
    assert pidfile.exists()
    assert metadata.exists()
    assert calls == []

    cleanup.cleanup_session()
    cleanup.cleanup_session()
    assert not socket.exists()
    assert not pidfile.exists()
    assert not metadata.exists()
    assert len([command for command in calls if "kill-session" in command]) == 1


def test_persist_success_leaves_session_socket_and_metadata_alive(
    tmp_path: Path,
) -> None:
    fake = PersistSuccessTmux()
    pid_dir = tmp_path / "runtime" / "claude"
    session_file = tmp_path / "session.jsonl"
    expected_socket = persistent_socket_path("homelab", "42")
    try:
        result = run_claude_agent(
            _config(tmp_path),
            _issue(),
            "prompt",
            run_func=fake,
            mkdtemp=lambda **_: str(tmp_path / "run"),
            nonce_factory=lambda: "nonce",
            clock=lambda: 0.0,
            sleep=lambda _: None,
            pidfile_dir=pid_dir,
            session_file=session_file,
            persist=True,
        )

        assert result.exit_code == 0
        assert expected_socket.exists()
        assert not any("kill-session" in command for command in fake.calls)
        assert not (tmp_path / "run").exists()
        metadata_path = pid_dir / f"{expected_socket.stem}.meta.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert metadata == {
            "binding": "homelab",
            "cwd": str(tmp_path),
            "issue_id": "42",
            "session_file": str(session_file),
            "session_name": expected_socket.stem,
        }
    finally:
        expected_socket.unlink(missing_ok=True)


def test_persist_launch_failure_removes_session_sidecar(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    pid_dir = tmp_path / "runtime" / "claude"
    expected_socket = persistent_socket_path("homelab", "42")

    def fail_launch(command, **kwargs):
        calls.append(command)
        if "new-session" in command:
            return Completed(stderr="boom", returncode=2)
        return Completed()

    result = run_claude_agent(
        _config(tmp_path),
        _issue(),
        "prompt",
        run_func=fail_launch,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        nonce_factory=lambda: "nonce",
        clock=lambda: 0.0,
        sleep=lambda _: None,
        pidfile_dir=pid_dir,
        persist=True,
    )

    assert result.exit_code == 1
    assert not (pid_dir / f"{expected_socket.stem}.meta.json").exists()
    assert any("kill-session" in command for command in calls)
    assert not (tmp_path / "run").exists()


def test_persist_timeout_removes_session_sidecar_and_socket(tmp_path: Path) -> None:
    fake = PersistSuccessTmux(result_text=None)
    pid_dir = tmp_path / "runtime" / "claude"
    expected_socket = persistent_socket_path("homelab", "42")
    times = chain([0.0, 0.0, 0.0, 0.0, 1.0], repeat(1.0))

    result = run_claude_agent(
        _config(tmp_path, timeout_ms=0),
        _issue(),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        nonce_factory=lambda: "nonce",
        clock=lambda: next(times),
        sleep=lambda _: None,
        pidfile_dir=pid_dir,
        persist=True,
    )

    assert result.exit_code == -1
    assert result.timed_out is True
    assert not expected_socket.exists()
    assert not (pid_dir / f"{expected_socket.stem}.meta.json").exists()
    assert any("kill-session" in command for command in fake.calls)
