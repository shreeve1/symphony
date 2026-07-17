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


# Speed up tests by using the actual sqlite3 in-memory bus instead of
# monkeypatching resolve_db_path; tests that need real disk use tmp_path.
_PODIUM_DB_PATH: Path | None = None


def _real_db_path() -> Path:
    return _PODIUM_DB_PATH or Path("podium.db").resolve()


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

    await scheduler._reconcile_startup(
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

    monkeypatch.setenv("SYMPHONY_WAKE_SENTINEL_PATH", str(tmp_path / "reply-wake"))
    monkeypatch.setattr(scheduler, "LOG_RETENTION_INTERVAL", timedelta(0))
    monkeypatch.setattr(scheduler, "_run_log_retention", fake_log_retention)
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


# ---------------------------------------------------------------------------
# Patrol Run retention tests
# ---------------------------------------------------------------------------


def _seed_patrol_runs(
    path: Path, log_root: Path, now: datetime, *, patrol_count: int
) -> int:
    """Seed a single patrol issue with ``patrol_count`` completed Runs.

    Returns the issue id.
    """
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('trading')")
        issue_id = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, origin, created_at, updated_at
            ) VALUES ('trading', 'Patrol issue', '', 'todo', 'patrol',
              '2026-06-01T00:00:00+00:00', '2026-06-01T00:00:00+00:00')
            """,
        ).lastrowid
        assert issue_id is not None
        issue_id = int(issue_id)
        for i in range(patrol_count):
            log_path = log_root / "patrol" / str(issue_id) / f"run-{i}.log"
            _touch(log_path, now)
            started_at = (now - timedelta(hours=patrol_count - i)).isoformat()
            connection.execute(
                """
                INSERT INTO run(issue_id, state, verdict, log_path, started_at)
                VALUES (?, 'succeeded', 'done', ?, ?)
                """,
                (issue_id, str(log_path), started_at),
            )
        connection.execute(
            "UPDATE issue SET latest_run_id = (SELECT MAX(id) FROM run WHERE issue_id = ?) WHERE id = ?",
            (issue_id, issue_id),
        )
        connection.commit()
        return issue_id
    finally:
        connection.close()


def _seed_patrol_runs_with_queued(path: Path, log_root: Path, now: datetime) -> int:
    """Seed a patrol issue with 5 completed + 1 queued Run."""
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('trading')")
        issue_id = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, origin, created_at, updated_at
            ) VALUES ('trading', 'Patrol with queued', '', 'running', 'patrol',
              '2026-06-01T00:00:00+00:00', '2026-06-01T00:00:00+00:00')
            """,
        ).lastrowid
        assert issue_id is not None
        issue_id = int(issue_id)
        for i in range(5):
            log_path = log_root / "patrol" / str(issue_id) / f"run-{i}.log"
            _touch(log_path, now)
            started_at = (now - timedelta(hours=5 - i)).isoformat()
            connection.execute(
                """
                INSERT INTO run(issue_id, state, verdict, log_path, started_at)
                VALUES (?, 'succeeded', 'done', ?, ?)
                """,
                (issue_id, str(log_path), started_at),
            )
        # Add a queued run (should be protected)
        queued_log = log_root / "patrol" / str(issue_id) / "run-queued.log"
        _touch(queued_log, now)
        connection.execute(
            """
            INSERT INTO run(issue_id, state, verdict, log_path, started_at, cost_usd)
            VALUES (?, 'queued', NULL, ?, ?, 0)
            """,
            (issue_id, str(queued_log), now.isoformat()),
        )
        connection.execute(
            "UPDATE issue SET latest_run_id = (SELECT MAX(id) FROM run WHERE issue_id = ?) WHERE id = ?",
            (issue_id, issue_id),
        )
        connection.commit()
        return issue_id
    finally:
        connection.close()


def _seed_non_patrol_issue(path: Path, log_root: Path, now: datetime) -> int:
    """Seed a non-patrol issue with 6 completed Runs (should not be pruned)."""
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('trading')")
        issue_id = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, origin, created_at, updated_at
            ) VALUES ('trading', 'Operator issue', '', 'todo', 'operator',
              '2026-06-01T00:00:00+00:00', '2026-06-01T00:00:00+00:00')
            """,
        ).lastrowid
        assert issue_id is not None
        issue_id = int(issue_id)
        for i in range(6):
            log_path = log_root / "operator" / str(issue_id) / f"run-{i}.log"
            _touch(log_path, now)
            started_at = (now - timedelta(hours=6 - i)).isoformat()
            connection.execute(
                """
                INSERT INTO run(issue_id, state, verdict, log_path, started_at)
                VALUES (?, 'succeeded', 'done', ?, ?)
                """,
                (issue_id, str(log_path), started_at),
            )
        connection.commit()
        return issue_id
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_patrol_prune_leaves_newest_three_completed(tmp_path: Path) -> None:
    """More than 3 completed patrol Runs leaves exactly the newest 3 rows and
    logs after pruning."""
    now = datetime(2026, 6, 11, tzinfo=UTC)
    db_path = tmp_path / "podium.db"
    log_root = tmp_path / "runs"
    issue_id = _seed_patrol_runs(db_path, log_root, now, patrol_count=6)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="trading")

    counts = await adapter.prune_patrol_runs()

    assert counts["pruned_rows"] == 3
    assert counts["pruned_logs"] == 3
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        kept = connection.execute(
            "SELECT * FROM run WHERE issue_id = ? ORDER BY id ASC", (issue_id,)
        ).fetchall()
        assert len(kept) == 3
        # The 3 newest (highest id) should survive
        for row in kept:
            assert Path(str(row["log_path"])).is_file()


@pytest.mark.asyncio
async def test_patrol_prune_protects_queued_running(tmp_path: Path) -> None:
    """Queued/running Runs are never deleted; cleanup after completion converges
    to 3."""
    now = datetime(2026, 6, 11, tzinfo=UTC)
    db_path = tmp_path / "podium.db"
    log_root = tmp_path / "runs"
    issue_id = _seed_patrol_runs_with_queued(db_path, log_root, now)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="trading")

    counts = await adapter.prune_patrol_runs()

    # 5 completed - 3 kept = 2 pruned. Queued run remains.
    assert counts["pruned_rows"] == 2
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        kept = connection.execute(
            "SELECT id, state FROM run WHERE issue_id = ? ORDER BY id ASC",
            (issue_id,),
        ).fetchall()
        # 3 youngest completed + 1 queued = 4 total
        assert len(kept) == 4
        assert [r["state"] for r in kept] == [
            "succeeded",
            "succeeded",
            "succeeded",
            "queued",
        ]


@pytest.mark.asyncio
async def test_patrol_prune_fewer_than_three_is_noop(tmp_path: Path) -> None:
    """Issues with <= 3 completed Runs are untouched."""
    now = datetime(2026, 6, 11, tzinfo=UTC)
    db_path = tmp_path / "podium.db"
    log_root = tmp_path / "runs"
    issue_id = _seed_patrol_runs(db_path, log_root, now, patrol_count=2)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="trading")

    counts = await adapter.prune_patrol_runs()

    assert counts["pruned_rows"] == 0
    assert counts["pruned_logs"] == 0
    with sqlite3.connect(db_path) as connection:
        kept = connection.execute(
            "SELECT COUNT(*) FROM run WHERE issue_id = ?", (issue_id,)
        ).fetchone()[0]
        assert kept == 2


@pytest.mark.asyncio
async def test_patrol_prune_repairs_latest_run_projection(tmp_path: Path) -> None:
    """When the deleted set includes the current latest_run_id, the projection
    is repaired from the newest surviving Run."""
    now = datetime(2026, 6, 11, tzinfo=UTC)
    db_path = tmp_path / "podium.db"
    log_root = tmp_path / "runs"
    issue_id = _seed_patrol_runs(db_path, log_root, now, patrol_count=5)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="trading")

    counts = await adapter.prune_patrol_runs()

    assert counts["pruned_rows"] == 2
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        issue = connection.execute(
            "SELECT latest_run_id, latest_run_state FROM issue WHERE id = ?",
            (issue_id,),
        ).fetchone()
        assert issue is not None
        # The surviving newest run
        survivor = connection.execute(
            "SELECT MAX(id) as id FROM run WHERE issue_id = ?", (issue_id,)
        ).fetchone()
        assert issue["latest_run_id"] == survivor["id"]


@pytest.mark.asyncio
async def test_patrol_prune_idempotent(tmp_path: Path) -> None:
    """Running patrol prune twice produces same result (second call is noop)."""
    now = datetime(2026, 6, 11, tzinfo=UTC)
    db_path = tmp_path / "podium.db"
    log_root = tmp_path / "runs"
    _seed_patrol_runs(db_path, log_root, now, patrol_count=6)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="trading")

    counts1 = await adapter.prune_patrol_runs()
    counts2 = await adapter.prune_patrol_runs()

    assert counts1["pruned_rows"] == 3
    assert counts2["pruned_rows"] == 0


@pytest.mark.asyncio
async def test_patrol_prune_leaves_non_patrol_untouched(tmp_path: Path) -> None:
    """Non-patrol Run rows are not pruned by patrol pruning."""
    now = datetime(2026, 6, 11, tzinfo=UTC)
    db_path = tmp_path / "podium.db"
    log_root = tmp_path / "runs"
    _seed_non_patrol_issue(db_path, log_root, now)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="trading")

    counts = await adapter.prune_patrol_runs()

    assert counts["pruned_rows"] == 0


@pytest.mark.asyncio
async def test_patrol_prune_missing_log_files(tmp_path: Path) -> None:
    """Missing log files don't crash pruning; they still count toward the cap."""
    now = datetime(2026, 6, 11, tzinfo=UTC)
    db_path = tmp_path / "podium.db"
    log_root = tmp_path / "runs"
    issue_id = _seed_patrol_runs(db_path, log_root, now, patrol_count=5)
    # Delete one log file to simulate missing
    run_logs = sorted((log_root / "patrol" / str(issue_id)).iterdir())
    if run_logs:
        run_logs[0].unlink()
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="trading")

    counts = await adapter.prune_patrol_runs()

    assert counts["pruned_rows"] == 2
    assert counts["pruned_logs"] < 2  # only existing log files were unlinked
