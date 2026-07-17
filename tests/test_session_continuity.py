from __future__ import annotations

import ast
import importlib.util
import re
import sys
import uuid
from pathlib import Path
from typing import Any, cast

_SPEC = importlib.util.spec_from_file_location(
    "session_continuity", Path(__file__).resolve().parents[1] / "session_continuity.py"
)
assert _SPEC is not None
assert _SPEC.loader is not None
continuity = importlib.util.module_from_spec(_SPEC)
sys.modules["session_continuity"] = continuity
_SPEC.loader.exec_module(continuity)
continuity = cast(Any, continuity)


def test_derive_session_id_is_deterministic_valid_and_distinct() -> None:
    first = continuity.derive_session_id("048")
    second = continuity.derive_session_id("048")
    other = continuity.derive_session_id("049")

    assert first == second
    assert uuid.UUID(first).version == 5
    assert first != other


def test_claude_session_file_path_uses_encoded_absolute_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "work repo"
    cwd.mkdir()
    monkeypatch.setenv("HOME", str(home))
    session_id = continuity.derive_session_id("048")

    path = continuity.session_file_path("claude", cwd, session_id)

    encoded_cwd = re.sub(r"[^A-Za-z0-9]", "-", str(cwd.resolve()))
    assert path == home / ".claude" / "projects" / encoded_cwd / f"{session_id}.jsonl"


def test_pi_session_file_path_uses_default_cwd_slug(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "work:repo"
    cwd.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("PI_CODING_AGENT_SESSION_DIR", raising=False)
    session_id = continuity.derive_session_id("048")

    path = continuity.session_file_path("pi", cwd, session_id)

    safe_path = (
        f"--{str(cwd.resolve()).lstrip('/').replace('/', '-').replace(':', '-')}--"
    )
    assert (
        path == home / ".pi" / "agent" / "sessions" / safe_path / f"{session_id}.jsonl"
    )


def test_pi_session_file_path_honors_session_dir_override(
    tmp_path: Path, monkeypatch
) -> None:
    cwd = tmp_path / "repo"
    session_dir = tmp_path / "pi-sessions"
    cwd.mkdir()
    monkeypatch.setenv("PI_CODING_AGENT_SESSION_DIR", str(session_dir))
    session_id = continuity.derive_session_id("048")

    assert (
        continuity.session_file_path("pi", cwd, session_id)
        == session_dir / f"{session_id}.jsonl"
    )


def test_pi_session_file_path_finds_existing_timestamped_session(
    tmp_path: Path, monkeypatch
) -> None:
    cwd = tmp_path / "repo"
    session_dir = tmp_path / "pi-sessions"
    cwd.mkdir()
    session_dir.mkdir()
    monkeypatch.setenv("PI_CODING_AGENT_SESSION_DIR", str(session_dir))
    session_id = continuity.derive_session_id("048")
    existing = session_dir / f"2026-06-13T00-00-00-000Z_{session_id}.jsonl"
    existing.write_text('{"type":"session"}\n')

    assert continuity.session_file_path("pi", cwd, session_id) == existing


def test_evaluate_resume_eligibility_resumes_when_all_conditions_hold(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "repo"
    cwd.mkdir()
    monkeypatch.setenv("HOME", str(home))
    session_id = continuity.derive_session_id("048")
    session_file = continuity.session_file_path("claude", cwd, session_id)
    session_file.parent.mkdir(parents=True)
    session_file.write_text('{"type":"session"}\n')

    decision = continuity.evaluate_resume_eligibility(
        previous_agent_kind="claude",
        current_agent_kind="claude",
        previous_cwd=cwd,
        current_cwd=cwd,
        session_id=session_id,
        agent_session_sha="abc123",
        current_git_sha="abc123",
    )

    assert decision.action == continuity.ACTION_RESUME
    assert decision.reason == continuity.REASON_ELIGIBLE
    assert decision.session_id == session_id
    assert decision.session_file == session_file


def test_evaluate_resume_eligibility_rejects_agent_mismatch(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    session_id = continuity.derive_session_id("048")

    decision = continuity.evaluate_resume_eligibility(
        previous_agent_kind="pi",
        current_agent_kind="claude",
        previous_cwd=cwd,
        current_cwd=cwd,
        session_id=session_id,
        agent_session_sha="abc123",
        current_git_sha="abc123",
    )

    assert decision.action == continuity.ACTION_REFEED
    assert decision.reason == continuity.REASON_AGENT_MISMATCH


def test_evaluate_resume_eligibility_rejects_missing_or_changed_cwd(
    tmp_path: Path,
) -> None:
    previous_cwd = tmp_path / "old"
    current_cwd = tmp_path / "new"
    current_cwd.mkdir()
    session_id = continuity.derive_session_id("048")

    decision = continuity.evaluate_resume_eligibility(
        previous_agent_kind="claude",
        current_agent_kind="claude",
        previous_cwd=previous_cwd,
        current_cwd=current_cwd,
        session_id=session_id,
        agent_session_sha="abc123",
        current_git_sha="abc123",
    )

    assert decision.action == continuity.ACTION_REFEED
    assert decision.reason == continuity.REASON_CWD_MISSING


def test_evaluate_resume_eligibility_rejects_absent_session(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    session_id = continuity.derive_session_id("048")

    decision = continuity.evaluate_resume_eligibility(
        previous_agent_kind="claude",
        current_agent_kind="claude",
        previous_cwd=cwd,
        current_cwd=cwd,
        session_id=session_id,
        agent_session_sha="abc123",
        current_git_sha="abc123",
    )

    assert decision.action == continuity.ACTION_REFEED
    assert decision.reason == continuity.REASON_SESSION_ABSENT


def test_evaluate_resume_eligibility_rejects_sha_drift(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "repo"
    cwd.mkdir()
    monkeypatch.setenv("HOME", str(home))
    session_id = continuity.derive_session_id("048")
    session_file = continuity.session_file_path("claude", cwd, session_id)
    session_file.parent.mkdir(parents=True)
    session_file.write_text('{"type":"session"}\n')

    decision = continuity.evaluate_resume_eligibility(
        previous_agent_kind="claude",
        current_agent_kind="claude",
        previous_cwd=cwd,
        current_cwd=cwd,
        session_id=session_id,
        agent_session_sha="abc123",
        current_git_sha="def456",
    )

    assert decision.action == continuity.ACTION_REFEED
    assert decision.reason == continuity.REASON_SHA_DRIFT


def test_patrol_generation_zero_matches_original() -> None:
    """Generation 0 produces the same id as non-generation derive_session_id."""
    original = continuity.derive_session_id("test-001")
    gen_zero = continuity.derive_session_id("test-001", generation=0)

    assert original == gen_zero


def test_patrol_generations_are_distinct() -> None:
    """Different generations produce different session ids for the same issue."""
    gen0 = continuity.derive_session_id("test-001", generation=0)
    gen1 = continuity.derive_session_id("test-001", generation=1)
    gen2 = continuity.derive_session_id("test-001", generation=2)

    assert gen0 != gen1
    assert gen1 != gen2
    assert gen0 != gen2


def test_patrol_generation_is_stable() -> None:
    """Same generation for same issue is deterministic."""
    a = continuity.derive_session_id("test-001", generation=2)
    b = continuity.derive_session_id("test-001", generation=2)

    assert a == b


def test_patrol_generation_distinct_across_issues() -> None:
    """Different issues with same generation get different ids."""
    a = continuity.derive_session_id("issue-a", generation=1)
    b = continuity.derive_session_id("issue-b", generation=1)

    assert a != b


def test_patrol_generation_is_valid_uuid() -> None:
    import uuid

    g0 = continuity.derive_session_id("test-001", generation=0)
    g1 = continuity.derive_session_id("test-001", generation=1)

    assert uuid.UUID(g0).version == 5
    assert uuid.UUID(g1).version == 5


def test_session_continuity_module_stays_pure() -> None:
    tree = ast.parse(Path("session_continuity.py").read_text())
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    assert not (
        {"subprocess", "scheduler", "agent_runner", "socket", "httpx"} & imported_roots
    )
