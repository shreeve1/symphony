from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

import main
import scheduler
from agent_runner import AgentResult
from config import SymphonyConfig
from tracker_podium import PodiumTrackerAdapter
from web.api.schema import SCHEMA_SQL


def _config(tmp_path: Path) -> SymphonyConfig:
    config = SymphonyConfig(
        plane_api_url="https://plane.example.test",
        plane_api_key="fake-plane-key-for-tests",
        plane_workspace_slug="homelab",
        plane_project_id="podium-project",
        homelab_repo_path=tmp_path,
        pi_bin="pi",
        pi_provider="openai-codex",
        pi_model="gpt-5.5",
        run_timeout_ms=1000,
    )
    binding = replace(
        config.bindings[0],
        name="trading",
        repo_path=tmp_path,
        binding_type="coding",
        tracker="podium",
    )
    return config.for_binding(binding)


def _seed_db(path: Path) -> int:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('trading')")
        connection.execute("INSERT INTO skill(name, description, source) VALUES ('/dev-build', '', 'test')")
        cursor = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, preferred_agent,
              preferred_skill, comments_md, context_md, created_at, updated_at
            ) VALUES ('trading', 'Smoke cutover', 'Exercise trading dispatch', 'todo', 'pi', '/dev-build', '', '', '2026-06-11T00:00:00+00:00', '2026-06-11T00:00:00+00:00')
            """
        )
        connection.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_trading_podium_dispatch_records_run_log_and_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_db(db_path)
    run_log_root = tmp_path / "runs"
    monkeypatch.setattr(scheduler, "RUN_LOG_ROOT", run_log_root)
    (tmp_path / "WORKFLOW.md").write_text("Repo policy. mode={{issue.mode}}", encoding="utf-8")
    config = _config(tmp_path)
    binding = config.bindings[0]
    adapter = PodiumTrackerAdapter(
        db_path=db_path,
        binding_name="trading",
        contract=binding.tracker_contract,
    )

    def agent_runner(issue, rendered_prompt: str) -> AgentResult:
        assert issue.id == str(issue_id)
        assert "mode=build" in rendered_prompt
        return AgentResult(
            0,
            10,
            False,
            stdout=(
                "SYMPHONY_RESULT: done\n"
                "SYMPHONY_SUMMARY: trading podium dispatch ok\n"
                "SYMPHONY_COST_USD: 0.0123\n"
                "SYMPHONY_INPUT_TOKENS: 123\n"
                "SYMPHONY_OUTPUT_TOKENS: 45\n"
                "stdout body"
            ),
            stderr="stderr body",
        )

    result = await scheduler.run_tick(
        config,
        cast(Any, adapter),
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
    run = await adapter.get_run(str(issue["latest_run_id"]))

    assert result.dispatched is True
    assert result.issue_id == str(issue_id)
    assert issue["state"] == "in_review"
    assert issue["latest_run_state"] == "succeeded"
    assert issue["latest_verdict"] == "done"
    assert "trading podium dispatch ok" in issue["comments_md"]
    assert "stdout body" in issue["context_md"]
    assert "stderr body" in issue["context_md"]
    assert run is not None
    assert run["state"] == "succeeded"
    assert run["verdict"] == "done"
    assert run["summary"] == "trading podium dispatch ok"
    assert run["agent"] == "pi"
    assert run["provider"] == "openai-codex"
    assert run["model"] == "gpt-5.5"
    assert run["cost_usd"] == 0.0123
    assert run["input_tokens"] == 123
    assert run["output_tokens"] == 45
    assert run["started_at"] is not None
    assert run["ended_at"] is not None
    assert Path(run["log_path"]).is_absolute()
    log = Path(run["log_path"]).read_text(encoding="utf-8")
    assert "stdout body" in log
    assert "stderr body" in log


def test_trading_binding_uses_podium_without_plane_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {
        "PLANE_API_URL": "https://plane.example.test",
        "PLANE_API_KEY": "fake-plane-key-for-tests",
        "PLANE_WORKSPACE_SLUG": "homelab",
        "PI_BIN": "pi",
    }
    config = SymphonyConfig.from_env(env)
    trading = next(binding for binding in config.bindings if binding.name == "trading")
    monkeypatch.setattr(main, "verify_pi_support", lambda *args, **kwargs: None)

    def fail_plane_transport(*args, **kwargs):
        raise AssertionError("trading cutover must not build a Plane transport")

    monkeypatch.setattr(main, "HttpxPlaneTransport", fail_plane_transport)

    runtime = main._build_binding_runtime(config, trading)

    assert trading.tracker == "podium"
    assert runtime.transport is None
    assert isinstance(runtime.adapter, PodiumTrackerAdapter)
