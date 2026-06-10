from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from importlib import import_module
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

main = import_module("web.api.main")
app = cast(Any, main.app)


@pytest.fixture()
def client(monkeypatch, tmp_path) -> Iterator[TestClient]:
    monkeypatch.setenv("PODIUM_DB_PATH", str(tmp_path / "podium.db"))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def issue_id(client: TestClient) -> int:
    issues = client.get("/api/bindings/trading/issues").json()
    return issues[0]["id"]


# (field, valid value) — one happy-path case per editable field.
HAPPY_CASES = [
    ("title", "Renamed issue"),
    ("description", "New description."),
    ("description", None),
    ("state", "done"),
    ("priority", "urgent"),
    ("priority", None),
    ("preferred_agent", "claude"),
    ("preferred_model", "claude-fable-5"),
    ("preferred_skill", "tdd"),
    ("preferred_skill", None),
    ("reasoning_effort", "low"),
    ("worktree_active", True),
    ("max_duration_seconds", 3600),
    ("max_duration_seconds", None),
    ("base_branch", "develop"),
    ("base_branch", None),
    ("comments_md", "# Updated comments\n\nNew thread."),
    ("context_md", "# Updated context\n\nNew session log."),
]

# (field, invalid value, expected status) — one validation failure per field.
FAILURE_CASES = [
    ("title", "", 422),
    ("title", None, 422),
    ("description", 123, 422),
    ("state", "archived", 422),
    ("state", None, 422),
    ("priority", "critical", 422),
    ("preferred_agent", 42, 422),
    ("preferred_model", [], 422),
    ("preferred_skill", "no-such-skill", 422),
    ("reasoning_effort", "max", 422),
    ("worktree_active", "maybe", 422),
    ("max_duration_seconds", 0, 422),
    ("max_duration_seconds", "abc", 422),
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
        json={"state": "in_review", "priority": "high", "worktree_active": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "in_review"
    assert body["priority"] == "high"
    assert body["worktree_active"] is True


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
