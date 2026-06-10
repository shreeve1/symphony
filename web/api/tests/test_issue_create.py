from __future__ import annotations

from collections.abc import Iterator
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


def test_create_minimal_issue_applies_server_defaults(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/trading/issues",
        json={"title": "smoke", "preferred_skill": "/diagnose"},
    )
    assert response.status_code == 201
    body = response.json()

    assert isinstance(body["id"], int)
    assert body["binding_name"] == "trading"
    assert body["title"] == "smoke"
    assert body["preferred_skill"] == "/diagnose"
    # Server-side defaults (#014 spec).
    assert body["state"] == "todo"
    assert body["reasoning_effort"] == "high"
    assert body["worktree_active"] is False
    assert body["base_branch"] == "main"  # trading base_branch in bindings.yml
    assert body["created_at"] is not None
    assert body["updated_at"] is not None

    # Round-trip through SQLite via a fresh read.
    fetched = client.get(f"/api/issues/{body['id']}").json()
    assert fetched == body


def test_create_with_all_optional_fields(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/homelab/issues",
        json={
            "title": "full payload",
            "description": "All optional fields set.",
            "priority": "urgent",
            "preferred_skill": "tdd",
            "preferred_agent": "claude",
            "preferred_model": "claude-fable-5",
            "worktree_active": True,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["description"] == "All optional fields set."
    assert body["priority"] == "urgent"
    assert body["preferred_skill"] == "tdd"
    assert body["preferred_agent"] == "claude"
    assert body["preferred_model"] == "claude-fable-5"
    assert body["worktree_active"] is True


def test_created_issue_appears_in_binding_list(client: TestClient) -> None:
    created = client.post(
        "/api/bindings/trading/issues", json={"title": "listed"}
    ).json()
    listed = client.get("/api/bindings/trading/issues").json()
    assert created["id"] in [issue["id"] for issue in listed]
    # Freshly created issue has the newest updated_at, so it sorts first.
    assert listed[0]["id"] == created["id"]


def test_create_missing_title_returns_422(client: TestClient) -> None:
    response = client.post("/api/bindings/trading/issues", json={})
    assert response.status_code == 422


def test_create_unknown_binding_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/no-such-binding/issues", json={"title": "smoke"}
    )
    assert response.status_code == 404


def test_create_with_state_field_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/trading/issues", json={"title": "smoke", "state": "done"}
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail[0]["type"] == "extra_forbidden"
    assert detail[0]["loc"] == ["state"]


# (body, expected status) — one validation failure per rule.
FAILURE_CASES = [
    ({"title": ""}, 422),
    ({"title": None}, 422),
    ({"title": 7}, 422),
    ({"title": "ok", "description": 123}, 422),
    ({"title": "ok", "priority": "critical"}, 422),
    ({"title": "ok", "preferred_skill": "no-such-skill"}, 422),
    ({"title": "ok", "preferred_agent": 42}, 422),
    ({"title": "ok", "preferred_model": []}, 422),
    ({"title": "ok", "worktree_active": "maybe"}, 422),
    ({"title": "ok", "reasoning_effort": "high"}, 400),  # server-set field
    ({"title": "ok", "base_branch": "develop"}, 400),  # server-set field
    ({"title": "ok", "flavor": "grape"}, 400),  # unknown field
]


@pytest.mark.parametrize(("body", "expected_status"), FAILURE_CASES)
def test_create_rejects_invalid_body(
    client: TestClient, body: dict[str, Any], expected_status: int
) -> None:
    before = client.get("/api/bindings/trading/issues").json()

    response = client.post("/api/bindings/trading/issues", json=body)
    assert response.status_code == expected_status

    # Rejected POST must not insert anything.
    after = client.get("/api/bindings/trading/issues").json()
    assert after == before
