"""Dispatch-gate fail-loud contract: agent, model, and skill resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from config import ProjectBinding
from plane_adapter import CandidateIssue
from scheduler import _apply_dispatch_gate
from tracker_contract import DEFAULT_CONTRACT


@pytest.fixture()
def catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "models.yml"
    path.write_text(
        "models:\n"
        "  - id: claude-fable-5\n"
        "    agent: claude\n"
        "    default: true\n"
        "  - id: gpt-5.5\n"
        "    agent: pi\n"
        "    provider: openai-codex\n"
        "    default: true\n"
        "  - id: deepseek-v4-pro\n"
        "    agent: pi\n"
        "    provider: deepseek\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("model_catalog.MODELS_PATH", path)
    return path


def _binding(default_agent: str = "pi") -> ProjectBinding:
    return ProjectBinding(
        name="test",
        plane_project_id="unused",
        repo_path=Path("/tmp"),
        base_branch="main",
        tracker_contract=DEFAULT_CONTRACT,
        default_agent=default_agent,
        tracker="podium",
    )


def _candidate(**overrides) -> CandidateIssue:
    fields = {
        "id": "1",
        "identifier": "1",
        "name": "t",
        "description": "",
        "labels": (),
        "created_at": "",
    }
    fields.update(overrides)
    return CandidateIssue(**fields)


def test_claude_agent_and_model_pass_gate(catalog: Path) -> None:
    candidate, error = _apply_dispatch_gate(
        _candidate(labels=("agent:claude",)), _binding()
    )
    assert error is None
    assert candidate.resolved_provider == ""
    assert candidate.resolved_model == "claude-fable-5"


def test_unknown_model_blocks_loudly(catalog: Path) -> None:
    _, error = _apply_dispatch_gate(
        _candidate(preferred_model="gpt-9000"), _binding()
    )
    assert error is not None and "gpt-9000" in error


def test_claude_model_on_pi_agent_blocks(catalog: Path) -> None:
    _, error = _apply_dispatch_gate(
        _candidate(preferred_model="claude-fable-5"), _binding()
    )
    assert error is not None
    assert "claude-fable-5" in error
    assert "requires agent `claude` but the issue resolves to agent `pi`" in error


def test_missing_skill_row_blocks(catalog: Path) -> None:
    _, error = _apply_dispatch_gate(
        _candidate(preferred_skill="ghost-skill", skill_source=""), _binding()
    )
    assert error is not None and "ghost-skill" in error


def test_skill_source_missing_on_disk_blocks(catalog: Path, tmp_path: Path) -> None:
    _, error = _apply_dispatch_gate(
        _candidate(
            preferred_skill="dev-build",
            skill_source=str(tmp_path / "nope" / "SKILL.md"),
        ),
        _binding(),
    )
    assert error is not None and "missing" in error


def test_default_model_and_effort_suffix(catalog: Path) -> None:
    candidate, error = _apply_dispatch_gate(_candidate(), _binding())
    assert error is None
    assert candidate.resolved_provider == "openai-codex"
    assert candidate.resolved_model == "gpt-5.5:high"


def test_preferred_model_and_effort_resolve(catalog: Path, tmp_path: Path) -> None:
    skill_file = tmp_path / "skills" / "dev-build" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("---\nname: dev-build\n---\n", encoding="utf-8")
    candidate, error = _apply_dispatch_gate(
        _candidate(
            preferred_model="deepseek-v4-pro",
            reasoning_effort="low",
            preferred_skill="dev-build",
            skill_source=str(skill_file),
        ),
        _binding(),
    )
    assert error is None
    assert candidate.resolved_provider == "deepseek"
    assert candidate.resolved_model == "deepseek-v4-pro:low"
