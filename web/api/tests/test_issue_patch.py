from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

# (field, valid value) — one happy-path case per editable field.
HAPPY_CASES = [
    ("title", "Renamed issue"),
    ("description", "New description."),
    ("description", None),
    ("state", "done"),
    ("state", "archived"),
    ("priority", "urgent"),
    ("priority", None),
    ("preferred_agent", "claude"),
    ("preferred_model", "claude-fable-5"),
    ("preferred_skill", "tdd"),
    ("preferred_skill", None),
    ("reasoning_effort", "low"),
    ("worktree_active", True),
    ("approval_required", True),
    ("approved", True),
    ("auto_land", True),
    ("scheduled_for", "2026-06-12T00:00:00+00:00"),
    ("scheduled_for", None),
    ("base_branch", "develop"),
    ("base_branch", None),
    ("comments_md", "# Updated comments\n\nNew thread."),
    ("context_md", "# Updated context\n\nNew session log."),
    ("blocked_by", [1]),
    ("locks", ["web-api"]),
]

# (field, invalid value, expected status) — one validation failure per field.
FAILURE_CASES = [
    ("title", "", 422),
    ("title", None, 422),
    ("description", 123, 422),
    ("state", "invalid_state", 422),
    ("state", None, 422),
    ("priority", "critical", 422),
    ("preferred_agent", 42, 422),
    ("preferred_model", [], 422),
    ("preferred_skill", "no-such-skill", 422),
    ("reasoning_effort", "max", 422),
    ("worktree_active", "maybe", 422),
    ("approval_required", None, 422),
    ("approval_required", "maybe", 422),
    ("approved", None, 422),
    ("approved", "maybe", 422),
    ("auto_land", None, 422),
    ("auto_land", "maybe", 422),
    ("scheduled_for", [], 422),
    ("base_branch", 7, 422),
    ("comments_md", None, 422),
    ("context_md", 5, 422),
]


@pytest.mark.parametrize(("field", "value"), HAPPY_CASES)
def test_patch_field_round_trips(
    client: TestClient, issue_id: int, field: str, value: Any
) -> None:
    response = client.patch(f"/api/issues/{issue_id}", json={field: value})
    assert response.status_code == 200
    assert response.json()[field] == value

    # Round-trip through SQLite via a fresh read.
    fetched = client.get(f"/api/issues/{issue_id}").json()
    assert fetched[field] == value


@pytest.mark.parametrize(("field", "value", "expected_status"), FAILURE_CASES)
def test_patch_field_rejects_invalid_value(
    client: TestClient, issue_id: int, field: str, value: Any, expected_status: int
) -> None:
    before = client.get(f"/api/issues/{issue_id}").json()

    response = client.patch(f"/api/issues/{issue_id}", json={field: value})
    assert response.status_code == expected_status

    # Rejected PATCH must not write anything (including updated_at).
    after = client.get(f"/api/issues/{issue_id}").json()
    assert after == before


def test_patch_unknown_field_returns_400_with_pydantic_error(
    client: TestClient, issue_id: int
) -> None:
    response = client.patch(f"/api/issues/{issue_id}", json={"flavor": "grape"})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail[0]["type"] == "extra_forbidden"
    assert detail[0]["loc"] == ["flavor"]


def test_patch_multiple_fields_at_once(client: TestClient, issue_id: int) -> None:
    response = client.patch(
        f"/api/issues/{issue_id}",
        json={
            "state": "in_review",
            "priority": "high",
            "worktree_active": True,
            "approval_required": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "in_review"
    assert body["priority"] == "high"
    assert body["worktree_active"] is True
    assert body["approval_required"] is True


def test_list_issues_filters_archived_state(client: TestClient, issue_id: int) -> None:
    response = client.patch(f"/api/issues/{issue_id}", json={"state": "archived"})
    assert response.status_code == 200

    archived = client.get("/api/bindings/symphony/issues?state=archived")
    assert archived.status_code == 200
    archived_issues = archived.json()
    assert archived_issues
    assert {issue["state"] for issue in archived_issues} == {"archived"}
    assert issue_id in {issue["id"] for issue in archived_issues}

    invalid = client.get("/api/bindings/symphony/issues?state=invalid_state")
    assert invalid.status_code == 422


def test_patch_updated_at_increases_monotonically(
    client: TestClient, issue_id: int
) -> None:
    stamps = []
    for state in ("todo", "blocked", "done"):
        response = client.patch(f"/api/issues/{issue_id}", json={"state": state})
        assert response.status_code == 200
        stamps.append(datetime.fromisoformat(response.json()["updated_at"]))
    assert stamps[0] < stamps[1] < stamps[2]


def test_patch_missing_issue_returns_404(client: TestClient) -> None:
    response = client.patch("/api/issues/999999", json={"state": "done"})
    assert response.status_code == 404


def test_patch_noop_does_not_bump_updated_at(client: TestClient, issue_id: int) -> None:
    before = client.get(f"/api/issues/{issue_id}").json()

    # Empty body: nothing to write, row returned unchanged.
    empty = client.patch(f"/api/issues/{issue_id}", json={})
    assert empty.status_code == 200
    assert empty.json() == before

    # Echoing the stored value: also a no-op.
    echo = client.patch(f"/api/issues/{issue_id}", json={"state": before["state"]})
    assert echo.status_code == 200
    assert echo.json()["updated_at"] == before["updated_at"]


def test_patch_rejects_blocked_by_cycle(client: TestClient, issue_id: int) -> None:
    child = client.post(
        "/api/bindings/symphony/issues",
        json={"title": "child", "blocked_by": [issue_id]},
    ).json()
    before = client.get(f"/api/issues/{issue_id}").json()

    response = client.patch(
        f"/api/issues/{issue_id}", json={"blocked_by": [child["id"]]}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "blocked_by cycle detected"
    assert client.get(f"/api/issues/{issue_id}").json() == before


def test_patch_coerces_worktree_active_off_for_remote_binding(
    client: TestClient, monkeypatch
) -> None:
    # Remote bindings (ADR-0012) defer worktrees: a PATCH setting
    # worktree_active=true on a remote binding's issue is coerced to False.
    import os
    from pathlib import Path

    import web.api.main as main
    from web.api.tests.conftest import REMOTE_BINDING_ENTRY, REMOTE_BINDING_NAME

    db_path = Path(os.environ["PODIUM_DB_PATH"])
    with main.connect(db_path) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO binding(name) VALUES (?)", (REMOTE_BINDING_NAME,)
        )
        cursor = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, state, worktree_active, base_branch,
              comments_md, context_md, created_at, updated_at
            ) VALUES (?, 'remote', 'todo', FALSE, 'main', '', '',
              '2026-06-11T00:00:00+00:00', '2026-06-11T00:00:00+00:00')
            """,
            (REMOTE_BINDING_NAME,),
        )
        connection.commit()
        remote_issue_id = cursor.lastrowid
    monkeypatch.setattr(main, "_bindings_override", [REMOTE_BINDING_ENTRY])

    response = client.patch(
        f"/api/issues/{remote_issue_id}", json={"worktree_active": True}
    )
    assert response.status_code == 200
    assert response.json()["worktree_active"] is False
    # Round-trip: nothing written through.
    fetched = client.get(f"/api/issues/{remote_issue_id}").json()
    assert fetched["worktree_active"] is False


def test_list_skills_returns_catalog(client: TestClient) -> None:
    response = client.get("/api/skills")
    assert response.status_code == 200
    skills = response.json()
    names = [skill["name"] for skill in skills]
    assert names == sorted(names)
    assert {"tdd", "code-review", "blueprint"}.issubset(set(names))
