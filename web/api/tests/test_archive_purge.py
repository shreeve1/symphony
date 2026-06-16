"""Tests for 14-day archived-issue retention purge (#036).

Covers FK-safe per-issue deletion, startup and post-PATCH sweeps, log file
cleanup, rollback on mid-purge failure, and defensive worktree removal.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import web.api.main as main
from web.api.tests.conftest import login

app = main.app


def _init_repo(path: Path) -> None:
    """Create a git repo at ``path`` with an initial commit on ``main``."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "test@test")
    _git(path, "config", "user.name", "Test")
    readme = path / "README.md"
    readme.write_text("# test", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "initial")


def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )


def _old_ts(days_ago: int = 15) -> str:
    """Return an ISO timestamp ``days_ago`` days in the past."""
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()


def _now_ts() -> str:
    """Return current ISO timestamp."""
    return datetime.now(UTC).isoformat()


def _seed_issue(
    db_path: Path,
    binding_name: str,
    *,
    state: str = "archived",
    days_ago: int = 15,
    with_runs: bool = True,
) -> dict[str, Any]:
    """Insert an issue (and optional runs) into podium.db. Returns the row."""
    conn = main.connect(db_path)
    try:
        updated_at = _old_ts(days_ago)
        created_at = _old_ts(days_ago + 1)
        cursor = conn.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, priority, preferred_agent,
              reasoning_effort, worktree_active, base_branch, comments_md, context_md,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'med', 'pi', 'high', FALSE, 'main', '', '', ?, ?)
            """,
            (
                binding_name,
                f"purge-test-{days_ago}d",
                "test",
                state,
                created_at,
                updated_at,
            ),
        )
        issue_id = int(cursor.lastrowid)

        run_ids: list[int] = []
        if with_runs:
            for _ in range(2):
                log_path = str(db_path.parent / "runs" / f"{issue_id}_test.log")
                Path(log_path).parent.mkdir(parents=True, exist_ok=True)
                Path(log_path).write_text("test log content\n")
                cursor = conn.execute(
                    """
                    INSERT INTO run(
                      issue_id, agent, state, verdict,
                      log_path, started_at, ended_at
                    ) VALUES (?, 'pi', 'succeeded', 'done', ?, ?, ?)
                    """,
                    (issue_id, log_path, _old_ts(days_ago), _old_ts(days_ago - 1)),
                )
                run_ids.append(int(cursor.lastrowid))

        if run_ids:
            conn.execute(
                "UPDATE issue SET latest_run_id = ? WHERE id = ?",
                (run_ids[-1], issue_id),
            )
        conn.commit()

        row = dict(
            conn.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
        )
        if with_runs:
            row["runs"] = [
                dict(conn.execute("SELECT * FROM run WHERE id = ?", (rid,)).fetchone())
                for rid in run_ids
            ]
        return row
    finally:
        conn.close()


def _binding_entry(name: str, repo_path: Path | None = None) -> dict:
    entry: dict[str, Any] = {
        "name": name,
        "plane_project_id": "fake-project",
        "base_branch": "main",
        "default_agent": "pi",
        "type": "coding",
        "tracker": "podium",
    }
    if repo_path is not None:
        entry["repo_path"] = str(repo_path)
    return entry


def _remote_binding_entry(name: str) -> dict:
    """Remote binding (ADR-0012): repo_path lives on another host; local git or
    Path ops against it would fail, so purge must skip worktree teardown."""
    return {
        "name": name,
        "repo_path": "/home/itadmin/itastack",
        "base_branch": "main",
        "default_agent": "pi",
        "type": "coding",
        "pi_mode": "one-shot",
        "tracker": "podium",
        "remote": {"user": "itadmin", "host": "100.95.224.218"},
    }


# ────────────────────────────── helpers ──────────────────────────────


def _count_issues(db_path: Path, issue_id: int | None = None) -> int:
    conn = main.connect(db_path)
    try:
        if issue_id is not None:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM issue WHERE id = ?", (issue_id,)
                ).fetchone()[0]
            )
        return int(conn.execute("SELECT COUNT(*) FROM issue").fetchone()[0])
    finally:
        conn.close()


def _count_runs(db_path: Path, issue_id: int) -> int:
    conn = main.connect(db_path)
    try:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM run WHERE issue_id = ?", (issue_id,)
            ).fetchone()[0]
        )
    finally:
        conn.close()


def _latest_run_id(db_path: Path, issue_id: int) -> int | None:
    conn = main.connect(db_path)
    try:
        row = conn.execute(
            "SELECT latest_run_id FROM issue WHERE id = ?", (issue_id,)
        ).fetchone()
        return row["latest_run_id"] if row else None
    finally:
        conn.close()


def _seed_binding(db_path: Path, name: str = "trading") -> None:
    conn = main.connect(db_path)
    try:
        main.ensure_schema(conn)
        conn.execute(
            "INSERT OR IGNORE INTO binding(name, display_name, sort_order) "
            "VALUES (?, ?, 0)",
            (name, name),
        )
        conn.commit()
    finally:
        conn.close()


# ────────────────────────────── fixtures ──────────────────────────────


@pytest.fixture(autouse=True)
def _clear_global_state():
    main.websocket_hub._subscribers.clear()
    main._bindings_override = None
    yield
    main.websocket_hub._subscribers.clear()
    main._bindings_override = None


@pytest.fixture
def db_and_client(monkeypatch, tmp_path: Path) -> Iterator[tuple[Path, TestClient]]:
    """A podium.db with binding + one issue, ready for PATCH-based tests."""
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    with TestClient(app) as client:
        login(client)
        _seed_binding(db_path)
        # create a fresh issue via the API
        resp = client.post("/api/bindings/trading/issues", json={"title": "test issue"})
        assert resp.status_code == 201
        yield db_path, client


# ──────────────────────── acceptance tests ────────────────────────


def test_purge_old_archived_issue(monkeypatch, tmp_path: Path) -> None:
    """Archived issue older than 14 days is deleted with its runs and logs."""
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("trading")])
    _seed_binding(db_path)
    issue = _seed_issue(db_path, "trading", days_ago=15)

    # Verify data exists before purge
    assert _count_issues(db_path, issue["id"]) == 1
    assert _count_runs(db_path, issue["id"]) == 2

    # Pre-built DB, so startup sweep happens when TestClient opens
    with TestClient(app):
        login(TestClient(app))

    assert _count_issues(db_path, issue["id"]) == 0

    # Log files deleted
    for run in issue.get("runs", []):
        log_path = run.get("log_path")
        if log_path:
            assert not Path(log_path).is_file()


def test_purge_young_archived_survives(monkeypatch, tmp_path: Path) -> None:
    """Archived issue younger than 14 days survives the sweep."""
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("trading")])
    _seed_binding(db_path)
    issue = _seed_issue(db_path, "trading", days_ago=5)

    with TestClient(app):
        login(TestClient(app))

    assert _count_issues(db_path, issue["id"]) == 1
    assert _count_runs(db_path, issue["id"]) == 2


def test_purge_non_archived_survives(monkeypatch, tmp_path: Path) -> None:
    """Non-archived issues (todo) survive regardless of age."""
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("trading")])
    _seed_binding(db_path)
    issue = _seed_issue(db_path, "trading", days_ago=30, state="todo")

    with TestClient(app):
        login(TestClient(app))

    assert _count_issues(db_path, issue["id"]) == 1


def test_purge_at_startup(monkeypatch, tmp_path: Path) -> None:
    """Sweep runs at API startup via lifespan."""
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("trading")])
    _seed_binding(db_path)

    # Two issues: old archived (purgeable), young archived (keep)
    old = _seed_issue(db_path, "trading", days_ago=20)
    young = _seed_issue(db_path, "trading", days_ago=5)

    with TestClient(app):
        login(TestClient(app))

    assert _count_issues(db_path, old["id"]) == 0
    assert _count_issues(db_path, young["id"]) == 1


def test_purge_after_patch_to_archived(db_and_client: tuple[Path, TestClient]) -> None:
    """PATCH that transitions an issue to archived triggers a purge sweep."""
    db_path, client = db_and_client
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("trading")])

    # Manually insert an old archived issue that should be purged
    old = _seed_issue(db_path, "trading", days_ago=20)

    # Get the fresh issue ID and archive it
    issues = client.get("/api/bindings/trading/issues").json()
    fresh_id = issues[0]["id"]
    resp = client.patch(f"/api/issues/{fresh_id}", json={"state": "archived"})
    assert resp.status_code == 200

    # The old archived issue should now be gone
    assert _count_issues(db_path, old["id"]) == 0

    monkeypatch.undo()


def test_purge_patch_response_unaffected(
    db_and_client: tuple[Path, TestClient],
) -> None:
    """PATCH response body is the just-archived issue, not affected by purge."""
    db_path, client = db_and_client
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("trading")])

    # Insert old archiveable issue
    _seed_issue(db_path, "trading", days_ago=20)

    # Archive a different issue
    issues = client.get("/api/bindings/trading/issues").json()
    fresh_ids = [i["id"] for i in issues]
    fresh_id = fresh_ids[0]

    resp = client.patch(f"/api/issues/{fresh_id}", json={"state": "archived"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == fresh_id
    assert body["state"] == "archived"

    monkeypatch.undo()


def test_purge_missing_log_does_not_abort(monkeypatch, tmp_path: Path) -> None:
    """Missing log file on disk does not abort the purge for other issues."""
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("trading")])
    _seed_binding(db_path)

    # Issue A: log_path points to a non-existent file
    issue_a = _seed_issue(db_path, "trading", days_ago=20)
    # Delete the log file for issue A runs
    for run in issue_a.get("runs", []):
        log_path = run.get("log_path")
        if log_path:
            Path(log_path).unlink(missing_ok=True)

    # Issue B: normal purgeable issue
    issue_b = _seed_issue(db_path, "trading", days_ago=20)

    with TestClient(app):
        login(TestClient(app))

    assert _count_issues(db_path, issue_a["id"]) == 0
    assert _count_issues(db_path, issue_b["id"]) == 0


def test_purge_mid_failure_rollback(monkeypatch, tmp_path: Path) -> None:
    """A mid-purge failure rolls back the transaction for that issue."""
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("trading")])
    _seed_binding(db_path)

    # Issue A: will succeed
    issue_a = _seed_issue(db_path, "trading", days_ago=20)
    # Issue B: will fail during purge via FK constraint
    issue_b = _seed_issue(db_path, "trading", days_ago=20)

    # Create an external FK reference to issue B's runs so DELETE FROM run fails
    conn = main.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _purge_test_ref("
            "  id INTEGER PRIMARY KEY,"
            "  run_id INTEGER REFERENCES run(id)"
            ")"
        )
        for run in issue_b.get("runs", []):
            conn.execute(
                "INSERT INTO _purge_test_ref(run_id) VALUES (?)",
                (run["id"],),
            )
        conn.commit()
    finally:
        conn.close()

    with TestClient(app):
        login(TestClient(app))

    # Issue A: should be fully purged
    assert _count_issues(db_path, issue_a["id"]) == 0

    # Issue B: should still exist with latest_run_id intact
    assert _count_issues(db_path, issue_b["id"]) == 1
    assert _latest_run_id(db_path, issue_b["id"]) is not None
    assert _count_runs(db_path, issue_b["id"]) == 2

    # Clean up test scaffolding
    conn = main.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS _purge_test_ref")
        conn.commit()
    finally:
        conn.close()


def test_purge_no_orphan_runs_after_rollback(monkeypatch, tmp_path: Path) -> None:
    """Post-rollback: no orphan runs or nulled latest_run_id left behind."""
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("trading")])
    _seed_binding(db_path)

    # Single failing issue
    issue = _seed_issue(db_path, "trading", days_ago=20)

    conn = main.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _purge_test_ref("
            "  id INTEGER PRIMARY KEY,"
            "  run_id INTEGER REFERENCES run(id)"
            ")"
        )
        for run in issue.get("runs", []):
            conn.execute(
                "INSERT INTO _purge_test_ref(run_id) VALUES (?)",
                (run["id"],),
            )
        conn.commit()
    finally:
        conn.close()

    with TestClient(app):
        login(TestClient(app))

    # Issue still exists with runs and latest_run_id intact
    assert _count_issues(db_path, issue["id"]) == 1
    assert _latest_run_id(db_path, issue["id"]) is not None
    assert _count_runs(db_path, issue["id"]) == 2

    conn = main.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS _purge_test_ref")
        conn.commit()
    finally:
        conn.close()


def test_purge_defensive_worktree_removal(monkeypatch, tmp_path: Path) -> None:
    """Purged issue with worktree_active=True has worktree removed."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("trading", repo)])
    _seed_binding(db_path)

    # Create an archived issue with worktree_active=True
    conn = main.connect(db_path)
    try:
        updated_at = _old_ts(20)
        cursor = conn.execute(
            """
            INSERT INTO issue(
              binding_name, title, state, worktree_active, base_branch,
              comments_md, context_md, created_at, updated_at
            ) VALUES (?, 'wt-issue', 'archived', TRUE, 'main', '', '', ?, ?)
            """,
            ("trading", _old_ts(21), updated_at),
        )
        issue_id = int(cursor.lastrowid)
        conn.commit()
    finally:
        conn.close()

    # Create a worktree for this issue
    from web.api.worktree import create_worktree

    wt_path = create_worktree(repo, "trading", str(issue_id), "main")
    assert wt_path.is_dir()

    with TestClient(app):
        login(TestClient(app))

    assert _count_issues(db_path, issue_id) == 0
    assert not wt_path.is_dir()


def test_purge_remote_binding_skips_worktree_teardown(
    monkeypatch, tmp_path: Path
) -> None:
    """Archived remote-binding rows are purged without any local worktree
    teardown — the remote repo_path is not local (ADR-0012)."""
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(main, "_bindings_override", [_remote_binding_entry("n8n")])
    _seed_binding(db_path, "n8n")

    # Stray worktree_active=True archived row for a remote binding.
    conn = main.connect(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO issue(
              binding_name, title, state, worktree_active, base_branch,
              comments_md, context_md, created_at, updated_at
            ) VALUES (?, 'remote-wt', 'archived', TRUE, 'main', '', '', ?, ?)
            """,
            ("n8n", _old_ts(21), _old_ts(20)),
        )
        issue_id = int(cursor.lastrowid)
        conn.commit()
    finally:
        conn.close()

    # Any local worktree op against the remote repo_path must be skipped.
    import web.api.worktree as wt

    def _boom(*_a, **_k):
        raise AssertionError("local worktree op ran for a remote binding")

    monkeypatch.setattr(wt, "worktree_exists", _boom)
    monkeypatch.setattr(wt, "remove_worktree", _boom)

    with TestClient(app):
        login(TestClient(app))

    assert _count_issues(db_path, issue_id) == 0


def test_purge_defensive_worktree_removal_ignores_stale_flag(
    monkeypatch, tmp_path: Path
) -> None:
    """Purged issue removes an existing worktree even if worktree_active is false."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("trading", repo)])
    _seed_binding(db_path)

    conn = main.connect(db_path)
    try:
        updated_at = _old_ts(20)
        cursor = conn.execute(
            """
            INSERT INTO issue(
              binding_name, title, state, worktree_active, base_branch,
              comments_md, context_md, created_at, updated_at
            ) VALUES (?, 'stale-wt-issue', 'archived', FALSE, 'main', '', '', ?, ?)
            """,
            ("trading", _old_ts(21), updated_at),
        )
        issue_id = int(cursor.lastrowid)
        conn.commit()
    finally:
        conn.close()

    from web.api.worktree import create_worktree

    wt_path = create_worktree(repo, "trading", str(issue_id), "main")
    assert wt_path.is_dir()

    with TestClient(app):
        login(TestClient(app))

    assert _count_issues(db_path, issue_id) == 0
    assert not wt_path.is_dir()
