from __future__ import annotations

import json
import os
import logging
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
from web.api.steer_queue import steer_queue_path, write_steer_record


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


class ReattachPasteFailureTmux(ReattachSuccessTmux):
    def __init__(self):
        super().__init__()
        self.failed_reattach = False
        self.launched = False

    def __call__(self, command, **kwargs):
        if command[:1] == ["tmux"] and "paste-buffer" in command and not self.launched:
            self.calls.append(command)
            self.failed_reattach = True
            return Completed(stderr="no server running", returncode=1)
        if command[:1] == ["tmux"] and "new-session" in command:
            self.launched = True
            return PersistSuccessTmux.__call__(self, command, **kwargs)
        if (
            command[:1] == ["tmux"]
            and self.launched
            and "display-message" not in command
        ):
            return PersistSuccessTmux.__call__(self, command, **kwargs)
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


def test_reattach_paste_failure_cleans_up_and_falls_back_to_cold_start(
    tmp_path: Path, monkeypatch
) -> None:
    fake = ReattachPasteFailureTmux()
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
        assert fake.failed_reattach is True
        assert any("kill-session" in command for command in fake.calls)
        assert any("new-session" in command for command in fake.calls)
        assert expected_socket.exists()
        assert (pid_dir / f"{expected_socket.stem}.pid").read_text(
            encoding="utf-8"
        ) == f"{os.getpid()} 12345"
        assert (pid_dir / f"{expected_socket.stem}.meta.json").exists()
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


class SteerTmux:
    def __init__(self, *, complete_on: str = "steer", stale_done0: bool = False):
        self.calls: list[list[str]] = []
        self.complete_on = complete_on
        self.stale_done0 = stale_done0
        self.loaded_prompts: list[str] = []
        self.current_result: Path | None = None
        self.current_done: Path | None = None

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if command[:1] != ["tmux"]:
            return Completed()
        if "new-session" in command:
            Path(command[2]).write_text("", encoding="utf-8")
            return Completed()
        if "display-message" in command:
            return Completed(stdout="")
        if "capture-pane" in command:
            return Completed(stdout="bypass permissions on")
        if "load-buffer" in command:
            prompt = Path(command[-1]).read_text(encoding="utf-8")
            self.loaded_prompts.append(prompt)
            self.current_result = _path_after(prompt, "literal result file path:")
            self.current_done = _path_after(prompt, "literal done file path:")
            return Completed()
        if "send-keys" in command:
            if command[-1] == "Escape":
                return Completed()
            assert self.current_result is not None
            assert self.current_done is not None
            prompt = self.loaded_prompts[-1]
            if self.stale_done0 and self.current_done.name == "done.0":
                self.current_result.write_text("stale gen0", encoding="utf-8")
                self.current_done.write_text("", encoding="utf-8")
            elif self.complete_on == "steer" and "Operator steer" in prompt:
                self.current_result.write_text(
                    "SYMPHONY_RESULT: done gen1", encoding="utf-8"
                )
                self.current_done.write_text("", encoding="utf-8")
            elif self.complete_on == "abort" and "Operator requested abort" in prompt:
                self.current_result.write_text(
                    "SYMPHONY_RESULT: blocked", encoding="utf-8"
                )
                self.current_done.write_text("", encoding="utf-8")
            elif self.complete_on == "nudge" and "appear to have stopped" in prompt:
                self.current_result.write_text(
                    "SYMPHONY_RESULT: done nudge", encoding="utf-8"
                )
                self.current_done.write_text("", encoding="utf-8")
            return Completed()
        if "has-session" in command:
            return Completed(returncode=0)
        return Completed()


def test_claude_steer_rotates_generation_ignores_done0_and_clears_queue(
    tmp_path: Path,
) -> None:
    environ = {"SYMPHONY_RUNTIME_DIR": str(tmp_path / "runtime")}
    write_steer_record(
        "run-1",
        "42",
        kind="steer",
        message="please adjust course",
        environ=environ,
    )
    fake = SteerTmux(stale_done0=True)

    result = run_claude_agent(
        _config(tmp_path),
        _issue(active_run_id="run-1"),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        nonce_factory=lambda: "nonce",
        clock=lambda: 0.0,
        sleep=lambda _: None,
        environ=environ,
    )

    assert result.exit_code == 0
    assert result.stdout == "SYMPHONY_RESULT: done gen1"
    steer_prompt = next(
        prompt for prompt in fake.loaded_prompts if "Operator steer" in prompt
    )
    assert "please adjust course" in steer_prompt
    assert "result.1.txt" in steer_prompt
    assert "done.1" in steer_prompt
    assert "result.0.txt" not in steer_prompt
    assert "done.0" not in steer_prompt
    assert not steer_queue_path("run-1", environ).exists()


def test_claude_abort_sends_escape_then_rotates_generation(tmp_path: Path) -> None:
    environ = {"SYMPHONY_RUNTIME_DIR": str(tmp_path / "runtime")}
    write_steer_record("run-2", "42", kind="abort", environ=environ)
    fake = SteerTmux(complete_on="abort")

    result = run_claude_agent(
        _config(tmp_path),
        _issue(active_run_id="run-2"),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        nonce_factory=lambda: "nonce",
        clock=lambda: 0.0,
        sleep=lambda _: None,
        environ=environ,
    )

    assert result.exit_code == 0
    escape_index = next(
        i for i, command in enumerate(fake.calls) if command[-1] == "Escape"
    )
    abort_prompt_index = [
        i for i, command in enumerate(fake.calls) if "load-buffer" in command
    ][1]
    assert escape_index < abort_prompt_index
    abort_prompt = next(
        prompt for prompt in fake.loaded_prompts if "Operator requested abort" in prompt
    )
    assert "result.1.txt" in abort_prompt
    assert "done.1" in abort_prompt


def test_claude_idle_nudge_after_steer_names_current_generation(
    tmp_path: Path,
) -> None:
    environ = {"SYMPHONY_RUNTIME_DIR": str(tmp_path / "runtime")}
    write_steer_record(
        "run-3",
        "42",
        kind="steer",
        message="wait for operator context",
        environ=environ,
    )
    fake = SteerTmux(complete_on="nudge")
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("", encoding="utf-8")

    result = run_claude_agent(
        _config(tmp_path),
        _issue(active_run_id="run-3"),
        "prompt",
        run_func=fake,
        mkdtemp=lambda **_: str(tmp_path / "run"),
        nonce_factory=lambda: "nonce",
        clock=lambda: 0.0,
        sleep=lambda _: None,
        environ=environ,
        session_file=transcript,
    )

    assert result.exit_code == 0
    nudge_prompt = next(
        prompt for prompt in fake.loaded_prompts if "appear to have stopped" in prompt
    )
    assert "result.1.txt" in nudge_prompt
    assert "done.1" in nudge_prompt
    assert "result.0.txt" not in nudge_prompt
    assert "done.0" not in nudge_prompt


def _write_meta(
    pid_dir: Path, socket: Path, *, issue_id: str, session_file: Path
) -> None:
    pid_dir.mkdir(parents=True, exist_ok=True)
    (pid_dir / f"{socket.stem}.meta.json").write_text(
        json.dumps(
            {
                "binding": "homelab",
                "cwd": "/unused/cwd",
                "issue_id": issue_id,
                "session_file": str(session_file),
                "session_name": socket.stem,
            }
        ),
        encoding="utf-8",
    )


def _patch_sweep_io(
    monkeypatch, tmp_path: Path, sockets: list[Path], reaped: list[str]
) -> Path:
    pid_dir = tmp_path / "runtime" / "claude"
    monkeypatch.setattr(
        claude_runner, "_claude_pidfile_dir", lambda environ=None: pid_dir
    )
    monkeypatch.setattr(
        claude_runner, "_default_claude_socket_glob", lambda pattern: sockets
    )
    monkeypatch.setattr(claude_runner, "_session_alive", lambda *args, **kwargs: True)

    def cleanup(socket_path, session_name, **kwargs):
        reaped.append(socket_path.stem)
        socket_path.unlink(missing_ok=True)
        pidfile = kwargs.get("pidfile_path")
        metadata = kwargs.get("metadata_path")
        if pidfile is not None:
            pidfile.unlink(missing_ok=True)
        if metadata is not None:
            metadata.unlink(missing_ok=True)

    monkeypatch.setattr(claude_runner, "_cleanup_claude_session_artifacts", cleanup)
    return pid_dir


def test_sweep_skips_running_issue_even_with_frozen_transcript(
    tmp_path: Path, monkeypatch
) -> None:
    socket = tmp_path / "symphony-claude-persist-homelab-42.sock"
    socket.write_text("", encoding="utf-8")
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("", encoding="utf-8")
    os.utime(transcript, (10.0, 10.0))
    reaped: list[str] = []
    pid_dir = _patch_sweep_io(monkeypatch, tmp_path, [socket], reaped)
    _write_meta(pid_dir, socket, issue_id="42", session_file=transcript)

    count = claude_runner.sweep_persistent_claude_sessions(
        "homelab",
        get_issue=lambda issue_id: {"state": "running", "latest_run_state": "running"},
        now=10_000.0,
        idle_ttl_s=30.0,
        max_live=0,
    )

    assert count == 0
    assert reaped == []
    assert socket.exists()


def test_sweep_reaps_terminal_missing_and_idle_but_keeps_fresh_parked(
    tmp_path: Path, monkeypatch
) -> None:
    sockets = [
        tmp_path / f"symphony-claude-persist-homelab-{issue}.sock"
        for issue in ("done", "missing", "idle", "fresh")
    ]
    for socket in sockets:
        socket.write_text("", encoding="utf-8")
    reaped: list[str] = []
    pid_dir = _patch_sweep_io(monkeypatch, tmp_path, sockets, reaped)
    for socket in sockets:
        transcript = tmp_path / f"{socket.stem}.jsonl"
        transcript.write_text("", encoding="utf-8")
        mtime = 10.0 if socket.stem.endswith("idle") else 95.0
        os.utime(transcript, (mtime, mtime))
        _write_meta(
            pid_dir,
            socket,
            issue_id=socket.stem.rsplit("-", 1)[1],
            session_file=transcript,
        )

    def get_issue(issue_id: str):
        if issue_id == "missing":
            return None
        if issue_id == "done":
            return {"state": "done", "latest_run_state": "succeeded"}
        return {"state": "in_review", "latest_run_state": "succeeded"}

    count = claude_runner.sweep_persistent_claude_sessions(
        "homelab",
        get_issue=get_issue,
        now=100.0,
        idle_ttl_s=30.0,
        max_live=8,
    )

    assert count == 3
    assert reaped == [
        "symphony-claude-persist-homelab-done",
        "symphony-claude-persist-homelab-missing",
        "symphony-claude-persist-homelab-idle",
    ]
    assert sockets[-1].exists()


def test_sweep_max_live_reaps_oldest_parked_only_and_logs(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    ids = ["running", "old", "new"]
    sockets = [
        tmp_path / f"symphony-claude-persist-homelab-{issue}.sock" for issue in ids
    ]
    for socket in sockets:
        socket.write_text("", encoding="utf-8")
    reaped: list[str] = []
    pid_dir = _patch_sweep_io(monkeypatch, tmp_path, sockets, reaped)
    mtimes = {"running": 1.0, "old": 2.0, "new": 3.0}
    for socket, issue_id in zip(sockets, ids, strict=True):
        transcript = tmp_path / f"{issue_id}.jsonl"
        transcript.write_text("", encoding="utf-8")
        os.utime(transcript, (mtimes[issue_id], mtimes[issue_id]))
        _write_meta(pid_dir, socket, issue_id=issue_id, session_file=transcript)

    def get_issue(issue_id: str):
        if issue_id == "running":
            return {"state": "running", "latest_run_state": "running"}
        return {"state": "in_review", "latest_run_state": "succeeded"}

    caplog.set_level(logging.INFO)
    count = claude_runner.sweep_persistent_claude_sessions(
        "homelab",
        get_issue=get_issue,
        now=10.0,
        idle_ttl_s=30.0,
        max_live=1,
    )

    assert count == 1
    assert reaped == ["symphony-claude-persist-homelab-old"]
    assert sockets[0].exists()
    assert "claude_persist_max_live_reaped" in caplog.text
    assert "old" in caplog.text


def test_sweep_uses_sidecar_issue_and_session_file_as_authority(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    socket = tmp_path / "symphony-claude-persist-homelab-lossy-999.sock"
    socket.write_text("", encoding="utf-8")
    authoritative_transcript = tmp_path / "worktree" / "session.jsonl"
    authoritative_transcript.parent.mkdir()
    authoritative_transcript.write_text("", encoding="utf-8")
    os.utime(authoritative_transcript, (1.0, 1.0))
    reaped: list[str] = []
    pid_dir = _patch_sweep_io(monkeypatch, tmp_path, [socket], reaped)
    _write_meta(pid_dir, socket, issue_id="42", session_file=authoritative_transcript)
    seen_issue_ids: list[str] = []

    def get_issue(issue_id: str):
        seen_issue_ids.append(issue_id)
        return {"state": "in_review", "latest_run_state": "succeeded"}

    caplog.set_level(logging.WARNING)
    count = claude_runner.sweep_persistent_claude_sessions(
        "homelab",
        get_issue=get_issue,
        now=100.0,
        idle_ttl_s=30.0,
        max_live=8,
    )

    assert count == 1
    assert seen_issue_ids == ["42"]
    assert reaped == ["symphony-claude-persist-homelab-lossy-999"]
    assert "claude_persist_socket_issue_mismatch" in caplog.text


def test_sweep_reaps_dead_socket_with_no_readable_sidecar(
    tmp_path: Path, monkeypatch
) -> None:
    socket = tmp_path / "symphony-claude-persist-homelab-42.sock"
    socket.write_text("", encoding="utf-8")
    reaped: list[str] = []
    pid_dir = _patch_sweep_io(monkeypatch, tmp_path, [socket], reaped)
    pid_dir.mkdir(parents=True, exist_ok=True)
    (pid_dir / f"{socket.stem}.meta.json").write_text("not json", encoding="utf-8")
    monkeypatch.setattr(claude_runner, "_session_alive", lambda *args, **kwargs: False)

    count = claude_runner.sweep_persistent_claude_sessions(
        "homelab",
        get_issue=lambda issue_id: {
            "state": "in_review",
            "latest_run_state": "succeeded",
        },
        now=100.0,
        idle_ttl_s=30.0,
        max_live=8,
    )

    assert count == 1
    assert reaped == ["symphony-claude-persist-homelab-42"]
