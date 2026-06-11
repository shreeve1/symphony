from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

main = import_module("web.api.main")
app = cast(Any, main.app)


@pytest.fixture()
def client(monkeypatch, tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    with TestClient(app) as test_client:
        yield test_client


def _first_issue_id(client: TestClient) -> int:
    issues = client.get("/api/bindings/trading/issues").json()
    return int(issues[0]["id"])


def _receive_json(ws, timeout: float = 1.0) -> dict[str, Any]:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(ws.receive_json)
        return cast(dict[str, Any], future.result(timeout=timeout))


def test_two_clients_receive_issue_updated_within_one_second(
    client: TestClient,
) -> None:
    issue_id = _first_issue_id(client)
    with (
        client.websocket_connect("/api/ws") as _client_a,
        client.websocket_connect("/api/ws") as client_b,
    ):
        response = client.patch(f"/api/issues/{issue_id}", json={"state": "blocked"})
        assert response.status_code == 200

        message = _receive_json(client_b)

    assert message["type"] == "issue.updated"
    assert message["id"] == issue_id
    assert message["row"]["state"] == "blocked"


@pytest.mark.parametrize(
    ("method", "path", "body", "event_type"),
    [
        ("patch", "/api/issues/{issue_id}", {"state": "blocked"}, "issue.updated"),
        (
            "post",
            "/api/bindings/trading/issues",
            {"title": "websocket created issue"},
            "issue.created",
        ),
    ],
)
def test_mutations_publish_one_event_per_successful_write(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    body: dict[str, Any],
    event_type: str,
) -> None:
    calls: list[dict[str, Any]] = []

    async def record(message: dict[str, Any]) -> None:
        calls.append(message)

    monkeypatch.setattr(main.websocket_hub, "publish", record)
    issue_id = _first_issue_id(client)
    resolved_path = path.format(issue_id=issue_id)

    response = getattr(client, method)(resolved_path, json=body)

    assert response.status_code in {200, 201}
    matches = [message for message in calls if message["type"] == event_type]
    assert len(matches) == 1


def test_reconnected_client_receives_updates(client: TestClient) -> None:
    issue_id = _first_issue_id(client)
    with client.websocket_connect("/api/ws") as client_a:
        client_a.close()

    with client.websocket_connect("/api/ws") as client_b:
        response = client.patch(f"/api/issues/{issue_id}", json={"state": "done"})
        assert response.status_code == 200

        message = _receive_json(client_b)

    assert message["type"] == "issue.updated"
    assert message["row"]["state"] == "done"


@pytest.mark.skipif(
    os.getenv("PODIUM_INTEGRATION") != "1",
    reason="requires live podium-api unit/process inspection",
)
def test_workers_assumption() -> None:
    output = subprocess.check_output(["pgrep", "-af", "uvicorn.*main:app"], text=True)
    workers = [line for line in output.splitlines() if "--workers" in line]
    assert len(workers) <= 1
    if workers:
        assert "--workers 1" in workers[0]
