from __future__ import annotations

import os
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

login = cast(Any, import_module("web.api.tests.conftest")).login

main = import_module("web.api.main")
app = cast(Any, main.app)


def test_read_endpoints_seed_temp_db(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))

    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        login(client)
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
    assert revision == main.INITIAL_REVISION

    env = {**os.environ, "PODIUM_DB_PATH": str(db_path)}
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd=Path(__file__).resolve().parents[3],
        env=env,
    )


def test_skills_endpoint_returns_rows_sorted_by_name(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))

    with TestClient(app) as client:
        login(client)
        with main.connect(db_path) as connection:
            connection.executemany(
                "INSERT INTO skill(name, description, source) VALUES (?, ?, ?)",
                [
                    ("zulu", "Zulu skill", "/tmp/zulu/SKILL.md"),
                    ("alpha", "Alpha skill", "/tmp/alpha/SKILL.md"),
                ],
            )
            connection.commit()

        response = client.get("/api/skills")

    assert response.status_code == 200
    assert response.json() == [
        {
            "name": "alpha",
            "description": "Alpha skill",
            "source": "/tmp/alpha/SKILL.md",
        },
        {"name": "zulu", "description": "Zulu skill", "source": "/tmp/zulu/SKILL.md"},
    ]


def test_concurrent_reads_do_not_cross_threads(monkeypatch, tmp_path: Path) -> None:
    # Regression: FastAPI runs the sync get_connection dependency and the sync
    # endpoint in different anyio threadpool threads. Without
    # check_same_thread=False on the SQLite connection, concurrent requests hit
    # "SQLite objects created in a thread can only be used in that same thread"
    # and return 500. Fire many requests in parallel so the threadpool spreads
    # them across worker threads and the cross-thread path is exercised.
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))

    with TestClient(app) as client:
        login(client)

        def fetch_bindings(_: int) -> int:
            return client.get("/api/bindings").status_code

        with ThreadPoolExecutor(max_workers=16) as pool:
            statuses = list(pool.map(fetch_bindings, range(64)))

    assert statuses == [200] * 64
