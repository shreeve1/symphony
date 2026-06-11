from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path

import pytest

import main
from agent_runner import AgentResult
from config import SymphonyConfig
from scheduler import run_tick
from web.api.schema import SCHEMA_SQL

PodiumTrackerAdapter = import_module("tracker_podium").PodiumTrackerAdapter


def _config(tmp_path: Path) -> SymphonyConfig:
    config = SymphonyConfig(
        plane_api_url="https://plane.example.test",
        plane_api_key="fake-plane-key-for-tests",
        plane_workspace_slug="homelab",
        plane_project_id="podium-project",
        homelab_repo_path=tmp_path,
        pi_bin="pi",
        pi_provider="zai",
        pi_model="glm-5.1:high",
        run_timeout_ms=1000,
    )
    binding = replace(
        config.bindings[0],
        name="test",
        repo_path=tmp_path,
        binding_type="coding",
        tracker="podium",
    )
    return config.for_binding(binding)


def _seed_db(path: Path) -> int:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('test')")
        connection.execute("INSERT INTO skill(name, description, source) VALUES ('/dev-build', '', 'test')")
        cursor = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, preferred_agent,
              preferred_skill, comments_md, context_md, created_at, updated_at
            ) VALUES ('test', 'Dispatch me', 'Exercise Podium dispatch', 'todo', 'pi', '/dev-build', '', '', '2026-06-11T00:00:00+00:00', '2026-06-11T00:00:00+00:00')
            """
        )
        connection.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_engine_dispatch_cycle_against_podium(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path)
    (tmp_path / "WORKFLOW.md").write_text("Repo policy. mode={{issue.mode}}", encoding="utf-8")
    config = _config(tmp_path)
    binding = config.bindings[0]
    adapter = PodiumTrackerAdapter(
        db_path=db_path,
        binding_name="test",
        contract=binding.tracker_contract,
    )
    prompts: list[str] = []

    def agent_runner(issue, rendered_prompt: str) -> AgentResult:
        prompts.append(rendered_prompt)
        return AgentResult(
            0,
            10,
            False,
            stdout="SYMPHONY_RESULT: done\nSYMPHONY_SUMMARY: podium dispatch ok\nfull output",
        )

    result = await run_tick(
        config,
        adapter,
        agent_runner=agent_runner,
        render_prompt=lambda issue: main._render_candidate_prompt(
            issue,
            contract=adapter.contract,
            repo_path=tmp_path,
            binding_type="coding",
            tracker_kind="podium",
        ),
        repo_dirty=lambda path: False,
        run_blocked_reconciler=False,
        now=lambda: datetime(2026, 6, 11, tzinfo=UTC),
    )
    issue = await adapter.get_issue(str(issue_id))

    assert result.dispatched is True
    assert result.issue_id == str(issue_id)
    assert issue["state"] == "in_review"
    assert "Symphony claimed at" in issue["comments_md"]
    assert "podium dispatch ok" in issue["comments_md"]
    assert "full output" in issue["context_md"]
    assert "mode=build" in prompts[0]
