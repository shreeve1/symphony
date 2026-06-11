from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

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


def _touch(path: Path, modified_at: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("log", encoding="utf-8")
    timestamp = modified_at.timestamp()
    path.touch()
    import os

    os.utime(path, (timestamp, timestamp))


def _seed_log_db(path: Path, log_root: Path, now: datetime) -> dict[int, list[int]]:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('trading')")
        issue_ids: list[int] = []
        for title in ("Many logs", "Old logs", "Recent logs"):
            issue_id = connection.execute(
                """
                INSERT INTO issue(
                  binding_name, title, description, state, comments_md, context_md,
                  created_at, updated_at
                ) VALUES ('trading', ?, '', 'done', '', '',
                  '2026-06-11T00:00:00+00:00', '2026-06-11T00:00:00+00:00')
                """,
                (title,),
            ).lastrowid
            assert issue_id is not None
            issue_ids.append(int(issue_id))

        runs_by_issue: dict[int, list[int]] = {issue_id: [] for issue_id in issue_ids}
        # 150 total logs across three issues: issue 1 has 120 young logs, issue 2
        # has 20 old logs, issue 3 has 10 young logs.
        specs = [
            (issue_ids[0], 120, now - timedelta(days=10)),
            (issue_ids[1], 20, now - timedelta(days=95)),
            (issue_ids[2], 10, now - timedelta(days=5)),
        ]
        sequence = 0
        for issue_id, count, mtime in specs:
            for index in range(count):
                sequence += 1
                log_path = log_root / str(issue_id) / f"run-{index}.log"
                _touch(log_path, mtime)
                started_at = (now - timedelta(minutes=sequence)).isoformat()
                run_id = connection.execute(
                    """
                    INSERT INTO run(issue_id, state, verdict, log_path, started_at)
                    VALUES (?, 'succeeded', 'done', ?, ?)
                    """,
                    (issue_id, str(log_path), started_at),
                ).lastrowid
                assert run_id is not None
                runs_by_issue[issue_id].append(int(run_id))
        connection.commit()
        return runs_by_issue
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_log_retention_prunes_old_logs_and_logs_beyond_recent_100(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 6, 11, tzinfo=UTC)
    db_path = tmp_path / "podium.db"
    log_root = tmp_path / "runs"
    _seed_log_db(db_path, log_root, now)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="trading")

    pruned = await adapter.prune_run_logs(now=now)

    assert pruned == 40
    cutoff = now - timedelta(days=90)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        issue_ids = [row["id"] for row in connection.execute("SELECT id FROM issue")]
        for issue_id in issue_ids:
            kept = connection.execute(
                "SELECT * FROM run WHERE issue_id = ? AND log_path IS NOT NULL",
                (issue_id,),
            ).fetchall()
            assert len(kept) <= 100
            for row in kept:
                path = Path(row["log_path"])
                assert path.is_file()
                assert datetime.fromtimestamp(path.stat().st_mtime, UTC) >= cutoff
        reaped = connection.execute(
            "SELECT id, log_path FROM run WHERE log_path IS NULL"
        ).fetchall()
    assert len(reaped) == 40


@pytest.mark.asyncio
async def test_reconcile_startup_invokes_log_retention_once(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 6, 11, tzinfo=UTC)
    db_path = tmp_path / "podium.db"
    log_root = tmp_path / "runs"
    _seed_log_db(db_path, log_root, now)
    config = _config(tmp_path)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="trading")

    await scheduler.reconcile_startup(
        config,
        cast(Any, adapter),
        now=lambda: now,
    )

    with sqlite3.connect(db_path) as connection:
        reaped = connection.execute(
            "SELECT COUNT(*) FROM run WHERE log_path IS NULL"
        ).fetchone()[0]
    assert reaped == 40


@pytest.mark.asyncio
async def test_run_loop_schedules_log_retention_every_24h(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StopLoop(Exception):
        pass

    calls: list[str] = []

    async def fake_log_retention(config, adapter, *, now):
        calls.append("retention")
        return 0

    async def fake_dispatch_one(
        config,
        adapter,
        agent_runner,
        render_prompt,
        notifier,
        run_blocked_reconciler,
        dispatch_state=None,
    ):
        return scheduler.TickResult(False, "no-candidates")

    async def fake_sleep(seconds):
        raise StopLoop

    monkeypatch.setattr(scheduler, "LOG_RETENTION_INTERVAL", timedelta(0))
    monkeypatch.setattr(scheduler, "run_log_retention", fake_log_retention)
    monkeypatch.setattr(scheduler, "_dispatch_one", fake_dispatch_one)
    monkeypatch.setattr(scheduler.asyncio, "sleep", fake_sleep)

    with pytest.raises(StopLoop):
        await scheduler.run_loop(
            _config(tmp_path),
            cast(Any, object()),
            agent_runner=lambda issue, prompt: AgentResult(0, 1, False),
            render_prompt=lambda issue: "prompt",
        )

    assert calls == ["retention"]
