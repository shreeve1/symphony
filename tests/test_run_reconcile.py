from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

import scheduler
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


def _seed_orphaned_run_db(path: Path, worktree_path: Path) -> tuple[int, int, int]:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('trading')")
        running_issue = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, worktree_active,
              comments_md, context_md, created_at, updated_at
            ) VALUES ('trading', 'Running orphan', '', 'running', 1, '', '',
              '2026-06-11T00:00:00+00:00', '2026-06-11T00:00:00+00:00')
            """
        ).lastrowid
        queued_issue = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, worktree_active,
              comments_md, context_md, created_at, updated_at
            ) VALUES ('trading', 'Queued orphan', '', 'todo', 0, '', '',
              '2026-06-11T00:00:00+00:00', '2026-06-11T00:00:00+00:00')
            """
        ).lastrowid
        assert running_issue is not None
        assert queued_issue is not None
        running_run = connection.execute(
            """
            INSERT INTO run(issue_id, state, worktree_path, started_at)
            VALUES (?, 'running', ?, '2026-06-11T00:00:00+00:00')
            """,
            (running_issue, str(worktree_path)),
        ).lastrowid
        queued_run = connection.execute(
            """
            INSERT INTO run(issue_id, state, started_at)
            VALUES (?, 'queued', '2026-06-11T00:00:01+00:00')
            """,
            (queued_issue,),
        ).lastrowid
        connection.execute(
            """
            UPDATE issue
            SET latest_run_id = ?, latest_run_state = 'running'
            WHERE id = ?
            """,
            (running_run, running_issue),
        )
        connection.execute(
            """
            UPDATE issue
            SET latest_run_id = ?, latest_run_state = 'queued'
            WHERE id = ?
            """,
            (queued_run, queued_issue),
        )
        connection.commit()
        assert running_run is not None
        assert queued_run is not None
        return int(running_issue), int(running_run), int(queued_run)
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_reconcile_startup_reaps_queued_and_running_podium_runs(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "podium.db"
    worktree_path = tmp_path / "worktrees" / "trading" / "1"
    worktree_path.mkdir(parents=True)
    running_issue, running_run, queued_run = _seed_orphaned_run_db(
        db_path, worktree_path
    )
    config = _config(tmp_path)
    binding = config.bindings[0]
    adapter = PodiumTrackerAdapter(
        db_path=db_path,
        binding_name="trading",
        contract=binding.tracker_contract,
    )
    now = datetime(2026, 6, 11, 12, 0, tzinfo=UTC)

    cleaned = await scheduler.reconcile_startup(
        config,
        cast(Any, adapter),
        now=lambda: now,
    )

    assert cleaned == 2
    assert worktree_path.is_dir()
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT * FROM run ORDER BY id").fetchall()
        issues = connection.execute("SELECT * FROM issue ORDER BY id").fetchall()

    for row in rows:
        assert row["state"] == "failed"
        assert row["verdict"] == "blocked"
        assert row["summary"] == "restart-orphan: reaped at 2026-06-11T12:00:00+00:00"
        assert row["ended_at"] == "2026-06-11T12:00:00+00:00"
    assert {row["id"] for row in rows} == {running_run, queued_run}
    for issue in issues:
        assert issue["state"] == "blocked"
        assert issue["latest_run_state"] == "failed"
        assert issue["latest_verdict"] == "blocked"
        assert (
            "Run reaped on restart at 2026-06-11T12:00:00+00:00" in issue["comments_md"]
        )
        assert "worktree preserved" in issue["comments_md"]
    assert issues[0]["id"] == running_issue


@pytest.mark.asyncio
async def test_reconcile_startup_logs_run_reconcile_pairs(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db_path = tmp_path / "podium.db"
    worktree_path = tmp_path / "worktrees" / "trading" / "1"
    worktree_path.mkdir(parents=True)
    _seed_orphaned_run_db(db_path, worktree_path)
    config = _config(tmp_path)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="trading")

    with caplog.at_level("INFO"):
        await scheduler.reconcile_startup(
            config,
            cast(Any, adapter),
            now=lambda: datetime(2026, 6, 11, 12, 0, tzinfo=UTC),
        )

    messages = [record.getMessage() for record in caplog.records]
    assert any("run_reconcile_begin binding=trading" in message for message in messages)
    assert any(
        "run_reconcile_done binding=trading reaped=2" in message for message in messages
    )
    assert any("log_retention_begin binding=trading" in message for message in messages)
    assert any("log_retention_done binding=trading" in message for message in messages)
