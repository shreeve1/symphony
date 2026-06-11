from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tracker_contract import PlaneLabel, TrackerRole
from tracker_podium import PodiumTrackerAdapter
from web.api.schema import SCHEMA_SQL


def _seed_issue(path: Path, *, scheduled_for: str | None = None) -> str:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name) VALUES ('homelab')")
        cursor = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, approval_required,
              approved, scheduled_for, created_at, updated_at
            ) VALUES ('homelab', 'Infra issue', '', 'todo', FALSE, FALSE, ?, ?, ?)
            """,
            (
                scheduled_for,
                "2026-06-11T00:00:00+00:00",
                "2026-06-11T00:00:00+00:00",
            ),
        )
        connection.commit()
        return str(cursor.lastrowid)
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_infra_approval_required_role_projects_to_column(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_issue(db_path)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="homelab")

    issue = await adapter.add_label(issue_id, TrackerRole.APPROVAL_REQUIRED)

    assert issue["approval_required"] == 1
    assert "approval-required" in issue["labels"]
    assert adapter.labels_contain_role(issue["labels"], TrackerRole.APPROVAL_REQUIRED)

    issue = await adapter.remove_label(issue_id, PlaneLabel.APPROVAL_REQUIRED)

    assert issue["approval_required"] == 0
    assert "approval-required" not in issue["labels"]


@pytest.mark.asyncio
async def test_infra_approved_role_projects_to_column(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    issue_id = _seed_issue(db_path)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="homelab")

    issue = await adapter.add_label(issue_id, TrackerRole.APPROVED)

    assert issue["approved"] == 1
    assert "approved" in issue["labels"]
    assert adapter.labels_contain_role(issue["labels"], TrackerRole.APPROVED)

    issue = await adapter.remove_label(issue_id, PlaneLabel.APPROVED)

    assert issue["approved"] == 0
    assert "approved" not in issue["labels"]


@pytest.mark.asyncio
async def test_infra_scheduled_role_projects_due_timestamp(tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    issue_id = _seed_issue(db_path, scheduled_for=future)
    adapter = PodiumTrackerAdapter(db_path=db_path, binding_name="homelab")

    future_issue = await adapter.get_issue(issue_id)
    assert "scheduled" not in future_issue["labels"]

    due_issue = await adapter.add_label(issue_id, TrackerRole.SCHEDULED)

    assert due_issue["scheduled_for"] is not None
    assert "scheduled" in due_issue["labels"]
    assert adapter.labels_contain_role(due_issue["labels"], TrackerRole.SCHEDULED)

    cleared = await adapter.remove_label(issue_id, PlaneLabel.SCHEDULED)

    assert cleared["scheduled_for"] is None
    assert "scheduled" not in cleared["labels"]
