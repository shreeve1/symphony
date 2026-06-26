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
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[3])}
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


def test_compact_endpoint_is_retired(client: TestClient) -> None:
    # The manual context-compaction endpoint was retired; the route no longer
    # exists. POSTing to it returns a client error instead of compacting.
    issue = client.post(
        "/api/bindings/symphony/issues", json={"title": "compact"}
    ).json()
    response = client.post(f"/api/issues/{issue['id']}/compact")
    assert response.status_code in (404, 405)
