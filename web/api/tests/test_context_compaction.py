from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from importlib import import_module
from pathlib import Path
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


def test_legacy_uvicorn_app_dir_import_loads_api_main() -> None:
    env = {**os.environ, "PYTHONPATH": ""}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import main; assert hasattr(main, 'app')",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr


def test_compact_issue_endpoint_returns_new_token_count(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    issue = client.post(
        "/api/bindings/symphony/issues", json={"title": "compact"}
    ).json()
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


def test_compact_issue_endpoint_returns_422_for_remote_binding(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Context compaction is deferred for remote bindings (ADR-0012): the manual
    # compaction endpoint refuses with 422 instead of routing through the remote
    # adapter.
    from types import SimpleNamespace

    from web.api.tests.conftest import REMOTE_BINDING_ENTRY, REMOTE_BINDING_NAME

    with main.connect() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO binding(name) VALUES (?)", (REMOTE_BINDING_NAME,)
        )
        connection.commit()
    issue = client.post(
        f"/api/bindings/{REMOTE_BINDING_NAME}/issues", json={"title": "compact"}
    ).json()
    issue_id = issue["id"]

    engine_main = import_module("main")
    # The endpoint resolves the binding from engine config; stub it so the
    # remote binding is present, then the _is_remote_binding guard fires.
    monkeypatch.setattr(
        engine_main.SymphonyConfig,
        "from_env",
        classmethod(
            lambda cls, *a, **k: SimpleNamespace(
                bindings=[SimpleNamespace(name=REMOTE_BINDING_NAME)]
            )
        ),
    )
    monkeypatch.setattr(main, "_bindings_override", [REMOTE_BINDING_ENTRY])

    response = client.post(f"/api/issues/{issue_id}/compact")
    assert response.status_code == 422
    assert REMOTE_BINDING_NAME in response.json()["detail"]
