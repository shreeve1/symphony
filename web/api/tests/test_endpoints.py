from __future__ import annotations

import os
import sqlite3
import subprocess
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

main = import_module("web.api.main")
app = cast(Any, main.app)


def test_read_endpoints_seed_temp_db(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))

    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        bindings_response = client.get("/api/bindings")
        assert bindings_response.status_code == 200
        bindings = bindings_response.json()
        binding_names = {binding["name"] for binding in bindings}
        assert {"homelab", "trading"}.issubset(binding_names)

        trading_issues_response = client.get("/api/bindings/trading/issues")
        assert trading_issues_response.status_code == 200
        trading_issues = trading_issues_response.json()
        assert len(trading_issues) >= 2
        assert all("latest_verdict" in issue for issue in trading_issues)
        assert all("latest_run_state" in issue for issue in trading_issues)

        issue_id = trading_issues[0]["id"]
        issue_response = client.get(f"/api/issues/{issue_id}")
        assert issue_response.status_code == 200
        issue = issue_response.json()
        assert issue["comments_md"]
        assert issue["context_md"]

        runs_response = client.get(f"/api/issues/{issue_id}/runs")
        assert runs_response.status_code == 200
        runs = runs_response.json()
        assert len(runs) >= 1
        assert runs[0]["state"] == "succeeded"
        assert runs[0]["verdict"] == "review"

    with sqlite3.connect(db_path) as connection:
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
    assert revision == "0001_initial"

    env = {**os.environ, "PODIUM_DB_PATH": str(db_path)}
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd=Path(__file__).resolve().parents[3],
        env=env,
    )
