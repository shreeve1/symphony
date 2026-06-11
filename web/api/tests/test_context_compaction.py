from __future__ import annotations

from collections.abc import Iterator
from importlib import import_module
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

main = import_module("web.api.main")
app = cast(Any, main.app)
login = cast(Any, import_module("web.api.tests.conftest")).login


@pytest.fixture()
def client(monkeypatch, tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    with TestClient(app) as test_client:
        login(test_client)
        yield test_client


def test_compact_issue_endpoint_returns_new_token_count(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    issue = client.post("/api/bindings/trading/issues", json={"title": "compact"}).json()
    issue_id = issue["id"]
    response = client.patch(
        f"/api/issues/{issue_id}", json={"context_md": "old context"}
    )
    assert response.status_code == 200

    async def fake_compact(target_issue_id: int) -> dict[str, Any]:
        with main.connect() as connection:
            connection.execute(
                "UPDATE issue SET context_md = ? WHERE id = ?",
                ("<!-- context compacted on test -->\nnew context", target_issue_id),
            )
            connection.commit()
        return {"issue_id": target_issue_id, "compacted": True, "token_count": 11}

    monkeypatch.setattr(main, "_compact_issue_context", fake_compact)

    compacted = client.post(f"/api/issues/{issue_id}/compact")

    assert compacted.status_code == 200
    assert compacted.json() == {
        "issue_id": issue_id,
        "compacted": True,
        "token_count": 11,
    }
    fetched = client.get(f"/api/issues/{issue_id}").json()
    assert fetched["context_md"].startswith("<!-- context compacted on test -->")


def test_compact_issue_endpoint_missing_issue_returns_404(client: TestClient) -> None:
    response = client.post("/api/issues/999999/compact")
    assert response.status_code == 404
