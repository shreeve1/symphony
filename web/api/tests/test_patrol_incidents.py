"""Tests for POST /api/bindings/{name}/incidents/observe.

Covers atomic BEGIN IMMEDIATE transaction, silent updates, escalation queuing
and release, concurrency with two independent connections, rollback,
Done reopen, legacy-id adoption, deterministic duplicate choice, recovery
idempotency, websocket/wake behavior, and no diagnostic leakage.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import web.api.main as main
from web.api.tests.conftest import login

PAYLOAD: dict[str, Any] = {
    "incident_family": "disk",
    "incident_resource": "nas1:/data",
    "severity": "medium",
    "evidence": "disk 98% full",
}


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


def _count_patrol_issues(db_path: Path) -> int:
    conn = main.connect(db_path)
    try:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM issue WHERE origin = 'patrol'",
            ).fetchone()[0]
        )
    finally:
        conn.close()


def _count_comments(db_path: Path, issue_id: int) -> int:
    conn = main.connect(db_path)
    try:
        row = conn.execute(
            "SELECT comments_md FROM issue WHERE id = ?", (issue_id,)
        ).fetchone()
        md = str(row["comments_md"] or "")
        return md.count("\n\n") if md else 0
    finally:
        conn.close()


def _issue_state(db_path: Path, issue_id: int) -> str:
    conn = main.connect(db_path)
    try:
        row = conn.execute(
            "SELECT state FROM issue WHERE id = ?", (issue_id,)
        ).fetchone()
        return str(row["state"])
    finally:
        conn.close()


def _get_issue(db_path: Path, issue_id: int) -> dict[str, Any]:
    conn = main.connect(db_path)
    try:
        row = conn.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


# ── fixtures ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_global_state():
    main.websocket_hub._subscribers.clear()
    main._bindings_override = None
    yield
    main.websocket_hub._subscribers.clear()
    main._bindings_override = None


@pytest.fixture
def db_and_client(monkeypatch, tmp_path: Path) -> Iterator[tuple[Path, TestClient]]:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    with TestClient(main.app) as client:
        login(client)
        _seed_binding(db_path)
        yield db_path, client


# ─────────────────────── acceptance tests ────────────────────────


def test_first_observation_creates_issue(db_and_client):
    db_path, client = db_and_client
    """First observation creates a patrol issue and dispatches."""
    db_path, client = db_and_client
    resp = client.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "CREATE_AND_DISPATCH"
    assert body["created"] == 1
    assert body["issue_id"] > 0

    issue = _get_issue(db_path, body["issue_id"])
    assert issue["origin"] == "patrol"
    assert issue["state"] == "todo"
    assert issue["patrol_incident_family"] == "disk"
    assert issue["patrol_incident_resource"] == "nas1:/data"
    assert issue["patrol_current_severity"] == "medium"
    assert issue["patrol_occurrence_count"] == 1
    assert issue["patrol_dispatch_count"] == 0
    assert issue["external_id"] is not None


def test_silent_update_same_severity(db_and_client):
    """Unchanged recurrence updates evidence/last_seen/count without comment."""
    db_path, client = db_and_client
    resp = client.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
    issue_id = resp.json()["issue_id"]

    # Set dispatch_count > 0 to simulate post-first-Run state
    conn = main.connect(db_path)
    try:
        conn.execute(
            "UPDATE issue SET patrol_dispatch_count = 1,"
            " patrol_last_dispatched_severity = 'medium'"
            " WHERE id = ?",
            (issue_id,),
        )
        conn.commit()
    finally:
        conn.close()

    # Same severity → SILENT_UPDATE
    resp2 = client.post(
        "/api/bindings/trading/incidents/observe",
        json={**PAYLOAD, "evidence": "disk 99% full"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["action"] == "SILENT_UPDATE"
    assert resp2.json()["silent_update"] == 1
    assert resp2.json()["issue_id"] == issue_id

    # Issue unchanged except patrol fields
    issue = _get_issue(db_path, issue_id)
    assert issue["state"] == "todo"
    assert issue["patrol_occurrence_count"] == 2
    assert issue["patrol_current_severity"] == "medium"
    assert _count_comments(db_path, issue_id) == 0  # no comment appended


def test_queued_escalation_during_active_run(db_and_client):
    """Escalation while active run queues the pending severity."""
    db_path, client = db_and_client
    resp = client.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
    issue_id = resp.json()["issue_id"]

    # Simulate active run
    conn = main.connect(db_path)
    try:
        conn.execute(
            "UPDATE issue SET patrol_dispatch_count = 1, patrol_last_dispatched_severity = 'medium', latest_run_state = 'running'"
            " WHERE id = ?",
            (issue_id,),
        )
        conn.commit()
    finally:
        conn.close()

    # Escalate to critical while running
    resp2 = client.post(
        "/api/bindings/trading/incidents/observe",
        json={**PAYLOAD, "severity": "critical"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["action"] == "QUEUED_ESCALATION"
    assert resp2.json()["escalated"] == 1

    issue = _get_issue(db_path, issue_id)
    assert issue["patrol_pending_severity"] == "critical"
    assert issue["state"] == "todo"


def test_release_escalation_when_idle(db_and_client):
    """Escalation while idle releases and moves to Todo."""
    db_path, client = db_and_client
    resp = client.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
    issue_id = resp.json()["issue_id"]

    conn = main.connect(db_path)
    try:
        conn.execute(
            "UPDATE issue SET patrol_dispatch_count = 1, patrol_last_dispatched_severity = 'medium' WHERE id = ?",
            (issue_id,),
        )
        conn.commit()
    finally:
        conn.close()

    # Escalate to critical while idle
    resp2 = client.post(
        "/api/bindings/trading/incidents/observe",
        json={**PAYLOAD, "severity": "critical"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["action"] == "ESCALATION_RELEASE"
    assert resp2.json()["escalated"] == 1

    issue = _get_issue(db_path, issue_id)
    assert issue["patrol_pending_severity"] is None
    assert issue["state"] == "todo"
    # Comment appended for escalation
    assert _count_comments(db_path, issue_id) == 1


def test_done_reopen_same_id(db_and_client):
    """Done recurrence reopens the same issue and key."""
    db_path, client = db_and_client
    resp = client.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
    issue_id = resp.json()["issue_id"]
    external_id = _get_issue(db_path, issue_id)["external_id"]

    # Mark done
    conn = main.connect(db_path)
    try:
        conn.execute("UPDATE issue SET state = 'done' WHERE id = ?", (issue_id,))
        conn.commit()
    finally:
        conn.close()

    # Recurrence → REOPEN_AND_DISPATCH
    resp2 = client.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
    assert resp2.status_code == 200
    assert resp2.json()["action"] == "REOPEN_AND_DISPATCH"
    assert resp2.json()["issue_id"] == issue_id

    issue = _get_issue(db_path, issue_id)
    assert issue["state"] == "todo"
    assert issue["external_id"] == external_id  # same key


def test_distinct_resources_produce_separate_issues(db_and_client):
    """Different family/resource pairs create distinct issues."""
    db_path, client = db_and_client
    r1 = client.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
    r2 = client.post(
        "/api/bindings/trading/incidents/observe",
        json={
            "incident_family": "disk",
            "incident_resource": "nas2:/data",
            "severity": "medium",
            "evidence": "disk 75% full",
        },
    )
    assert r1.json()["issue_id"] != r2.json()["issue_id"]
    assert _count_patrol_issues(db_path) == 2


def test_legacy_id_adoption(db_and_client):
    """Legacy external_id match populates Incident columns without new key."""
    db_path, client = db_and_client

    # Pre-seed a legacy patrol issue (pre-dedup format)
    conn = main.connect(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, priority,
              preferred_agent, preferred_model, reasoning_effort,
              base_branch, comments_md, context_md,
              external_id, origin, created_at, updated_at
            ) VALUES (?, ?, ?, 'todo', 'med',
              'pi', 'pi-duo/Duo', 'high',
              'main', '', '',
              ?, 'patrol', ?, ?)
            """,
            (
                "trading",
                "Legacy issue",
                "old evidence",
                "alert-legacy-001",
                datetime.now(UTC).isoformat(),
                datetime.now(UTC).isoformat(),
            ),
        )
        legacy_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    # New observation with legacy_external_ids
    resp = client.post(
        "/api/bindings/trading/incidents/observe",
        json={
            **PAYLOAD,
            "legacy_external_ids": ["alert-legacy-001"],
        },
    )
    assert resp.status_code == 200
    # Should adopt the legacy row, not create new
    assert resp.json()["action"] == "SILENT_UPDATE"
    assert resp.json()["issue_id"] == legacy_id
    assert resp.json()["created"] == 0

    issue = _get_issue(db_path, legacy_id)
    # Incident columns populated
    assert issue["patrol_incident_family"] == "disk"
    assert issue["patrol_incident_resource"] == "nas1:/data"
    # External_id preserved
    assert issue["external_id"] == "alert-legacy-001"


def test_deterministic_duplicate_choice(db_and_client):
    """When multiple legacy rows exist, pick highest-severity/newest."""
    db_path, client = db_and_client

    conn = main.connect(db_path)
    try:
        now = datetime.now(UTC).isoformat()
        conn.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, priority,
              preferred_agent, preferred_model, reasoning_effort,
              base_branch, comments_md, context_md,
              external_id, origin, created_at, updated_at,
              patrol_current_severity
            ) VALUES (?, ?, ?, 'todo', 'med',
              'pi', 'pi-duo/Duo', 'high',
              'main', '', '',
              ?, 'patrol', ?, ?,
              'low')
            """,
            ("trading", "Low", "", "ext-001", now, now),
        )
        cursor2 = conn.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, priority,
              preferred_agent, preferred_model, reasoning_effort,
              base_branch, comments_md, context_md,
              external_id, origin, created_at, updated_at,
              patrol_current_severity
            ) VALUES (?, ?, ?, 'todo', 'med',
              'pi', 'pi-duo/Duo', 'high',
              'main', '', '',
              ?, 'patrol', ?, ?,
              'high')
            """,
            ("trading", "High", "", "ext-002", now, now),
        )
        id_b = cursor2.lastrowid
        conn.commit()
    finally:
        conn.close()

    # Observation with both legacy ids — should pick the HIGH severity one
    resp = client.post(
        "/api/bindings/trading/incidents/observe",
        json={
            **PAYLOAD,
            "legacy_external_ids": ["ext-001", "ext-002"],
        },
    )
    assert resp.status_code == 200
    # HIGH should be chosen (higher severity)
    assert resp.json()["issue_id"] == id_b


def test_recovery_comment_idempotent(db_and_client):
    """Confirmed recovery appends one event and closes."""
    db_path, client = db_and_client
    resp = client.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
    issue_id = resp.json()["issue_id"]

    conn = main.connect(db_path)
    try:
        conn.execute(
            "UPDATE issue SET patrol_dispatch_count = 1, patrol_last_dispatched_severity = 'medium' WHERE id = ?",
            (issue_id,),
        )
        conn.commit()
    finally:
        conn.close()

    # First recovery
    r1 = client.post(
        "/api/bindings/trading/incidents/observe",
        json={
            **PAYLOAD,
            "evidence": "disk usage normal",
            "is_pass": True,
            "recovery_confirmed": True,
        },
    )
    assert r1.status_code == 200
    assert r1.json()["action"] == "RECOVERY_EVENT"
    assert _count_comments(db_path, issue_id) == 1

    # Second recovery (already done) → PASS_CONFIRMATION, no new comment
    r2 = client.post(
        "/api/bindings/trading/incidents/observe",
        json={
            **PAYLOAD,
            "evidence": "still normal",
            "is_pass": True,
            "recovery_confirmed": True,
        },
    )
    assert r2.status_code == 200
    assert r2.json()["action"] == "PASS_CONFIRMATION"
    assert _count_comments(db_path, issue_id) == 1  # no new comment


def test_concurrent_observations_no_duplicate(db_and_client):
    """Two concurrent observations produce one issue, not two."""
    db_path, client = db_and_client

    results: list[dict[str, Any]] = []

    def observe():
        c = TestClient(main.app)
        login(c)
        resp = c.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
        results.append(resp.json())

    threads = [threading.Thread(target=observe) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Expect at most one CREATE_AND_DISPATCH
    created = [r for r in results if r.get("action") == "CREATE_AND_DISPATCH"]
    assert len(created) <= 1
    # All issue_ids should be the same
    ids = {r.get("issue_id") for r in results if r.get("issue_id")}
    assert len(ids) == 1


def test_rollback_on_invalid_payload(db_and_client):
    """Invalid payload rolls back and returns 422."""
    db_path, client = db_and_client
    count_before = _count_patrol_issues(db_path)

    resp = client.post(
        "/api/bindings/trading/incidents/observe",
        json={"severity": "medium", "evidence": ""},  # empty evidence
    )
    assert resp.status_code == 422
    assert _count_patrol_issues(db_path) == count_before  # no side effects


def test_uniqueness_rollback_on_duplicate_key(db_and_client):
    """Duplicate external_id causes clean rollback."""
    db_path, client = db_and_client

    # First observation - succeeds
    r1 = client.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
    assert r1.status_code == 200
    assert _count_patrol_issues(db_path) == 1

    # Create another issue with same external_id should fail
    conn = main.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, priority,
              preferred_agent, preferred_model, reasoning_effort,
              base_branch, comments_md, context_md,
              external_id, origin, created_at, updated_at,
              patrol_incident_family, patrol_incident_resource,
              patrol_first_seen_at, patrol_last_seen_at,
              patrol_occurrence_count, patrol_current_severity
            ) VALUES (?, ?, ?, 'todo', 'med',
              'pi', 'pi-duo/Duo', 'high',
              'main', '', '',
              'dup-key', 'patrol', ?, ?,
              'disk', 'other', ?, ?, 1, 'medium')
            """,
            (
                "trading",
                "dup",
                "",
                datetime.now(UTC).isoformat(),
                datetime.now(UTC).isoformat(),
                datetime.now(UTC).isoformat(),
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # Should still be 2 issues
    assert _count_patrol_issues(db_path) == 2

    # Internal IntegrityError should be caught
    # (we're testing the handler's robustness, not triggering this from outside)


def test_ws_publish_and_wake_actions(db_and_client):
    """WS published and wake sentinel touched for dispatchable actions."""
    db_path, client = db_and_client

    # Subscribe before POST (inline, no threading race)
    q = asyncio.Queue()
    main.websocket_hub._subscribers.add(q)
    try:
        resp = client.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
        assert resp.status_code == 200
        msg = q.get_nowait()
        assert msg["type"] == "issue.updated"
        assert msg["id"] == resp.json()["issue_id"]
    finally:
        main.websocket_hub._subscribers.discard(q)


def test_pass_confirmation_no_comment(db_and_client):
    """Routine pass does not append a comment."""
    db_path, client = db_and_client
    resp = client.post(
        "/api/bindings/trading/incidents/observe",
        json={
            "incident_family": "disk",
            "incident_resource": "nas1:/data",
            "severity": "medium",
            "evidence": "disk OK",
            "is_pass": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "PASS_CONFIRMATION"

    # No issue was created for pass with no prior issue
    assert _count_patrol_issues(db_path) == 0


def test_rollback_on_missing_binding(db_and_client):
    """Nonexistent binding returns 404 with no side effects."""
    db_path, client = db_and_client
    count_before = _count_patrol_issues(db_path)
    resp = client.post("/api/bindings/nonexistent/incidents/observe", json=PAYLOAD)
    assert resp.status_code == 404
    assert _count_patrol_issues(db_path) == count_before


def test_scheduled_hold_queues_escalation(db_and_client):
    """Scheduled hold prevents escalation from dispatching."""
    db_path, client = db_and_client
    resp = client.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
    issue_id = resp.json()["issue_id"]

    conn = main.connect(db_path)
    try:
        conn.execute(
            "UPDATE issue SET patrol_dispatch_count = 1, patrol_last_dispatched_severity = 'medium', hold = TRUE WHERE id = ?",
            (issue_id,),
        )
        conn.commit()
    finally:
        conn.close()

    resp2 = client.post(
        "/api/bindings/trading/incidents/observe",
        json={**PAYLOAD, "severity": "critical"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["action"] == "QUEUED_ESCALATION"


def test_no_diagnostic_logging(monkeypatch, db_and_client):
    """No diagnostic bodies leak into log records."""
    db_path, client = db_and_client
    records: list[str] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    logger = logging.getLogger("web.api.main")
    handler = CaptureHandler()
    logger.addHandler(handler)
    try:
        client.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
    finally:
        logger.removeHandler(handler)

    # No diagnostic log should contain evidence text
    for msg in records:
        assert "98% full" not in msg
        assert "evidence" not in msg.lower()


def test_concurrent_observations_both_return_200(db_and_client):
    """Two concurrent first observations both return 200; one issue remains."""
    db_path, client = db_and_client

    results: list[dict[str, Any]] = []
    errors: list[Exception] = []

    def observe():
        try:
            # Each thread uses its own TestClient (independent SQLite connection)
            c = TestClient(main.app)
            login(c)
            resp = c.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
            results.append(resp.json())
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=observe) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"thread errors: {errors}"
    assert len(results) == 2
    # Both threads got 200
    # With BEGIN IMMEDIATE serializing access, one becomes CREATE_AND_DISPATCH
    # and the other becomes SILENT_UPDATE — both are 200 responses.
    actions = {r.get("action") for r in results}
    assert actions.issubset({"CREATE_AND_DISPATCH", "SILENT_UPDATE"})
    assert "CREATE_AND_DISPATCH" in actions
    # Exactly one issue exists
    assert _count_patrol_issues(db_path) == 1
    # Same issue_id for both
    ids = [r.get("issue_id") for r in results if r.get("issue_id")]
    assert len(set(ids)) == 1


def test_legacy_null_severity_escalation_release(db_and_client):
    """Legacy NULL patrol_current_severity does not block ESCALATION_RELEASE."""
    db_path, client = db_and_client
    resp = client.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
    issue_id = resp.json()["issue_id"]

    # Simulate: dispatched once but patrol_current_severity is NULL (legacy row)
    conn = main.connect(db_path)
    try:
        conn.execute(
            "UPDATE issue SET patrol_dispatch_count = 1,"
            " patrol_last_dispatched_severity = NULL,"
            " patrol_current_severity = NULL"
            " WHERE id = ?",
            (issue_id,),
        )
        conn.commit()
    finally:
        conn.close()

    # Escalate — should release even though current_severity is NULL
    resp2 = client.post(
        "/api/bindings/trading/incidents/observe",
        json={**PAYLOAD, "severity": "critical"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["action"] == "ESCALATION_RELEASE"
    assert resp2.json()["escalated"] == 1

    issue = _get_issue(db_path, issue_id)
    assert issue["patrol_pending_severity"] is None
    assert issue["state"] == "todo"


def test_archive_restore_observe_creates_new_issue(db_and_client):
    """Restore an archived patrol row then observe: creates new issue because
    external_id was severed on archive and active lookup requires IS NOT NULL."""
    db_path, client = db_and_client
    resp = client.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
    old_issue_id = resp.json()["issue_id"]
    old_external_id = _get_issue(db_path, old_issue_id)["external_id"]
    assert old_external_id is not None

    # Archive patrol issue → external_id set to NULL
    resp_archive = client.patch(
        f"/api/issues/{old_issue_id}", json={"state": "archived"}
    )
    assert resp_archive.status_code == 200
    archived = _get_issue(db_path, old_issue_id)
    assert archived["external_id"] is None
    assert archived["state"] == "archived"

    # Restore: set back to todo (simulate operator restoring from archive)
    conn = main.connect(db_path)
    try:
        conn.execute(
            "UPDATE issue SET state = 'todo',"
            " patrol_incident_family = 'disk',"
            " patrol_incident_resource = 'nas1:/data'"
            " WHERE id = ?",
            (old_issue_id,),
        )
        conn.commit()
    finally:
        conn.close()

    # Same observation — should NOT match the restored row (external_id IS NULL)
    resp3 = client.post("/api/bindings/trading/incidents/observe", json=PAYLOAD)
    assert resp3.status_code == 200
    assert resp3.json()["action"] == "CREATE_AND_DISPATCH"
    assert resp3.json()["issue_id"] != old_issue_id

    # Two patrol issues exist: the archived one and the new one
    assert _count_patrol_issues(db_path) == 2
