from __future__ import annotations

import sqlite3
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

main = import_module("web.api.main")
app = cast(Any, main.app)


def _seeded_run_id(db_path: Path) -> int:
    with sqlite3.connect(db_path) as connection:
        return int(connection.execute("SELECT id FROM run ORDER BY id LIMIT 1").fetchone()[0])


def _run_columns(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        return {row[1] for row in connection.execute("PRAGMA table_info(run)")}


def test_get_run_returns_full_row(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))

    with TestClient(app) as client:
        run_id = _seeded_run_id(db_path)
        response = client.get(f"/api/runs/{run_id}")

    assert response.status_code == 200
    assert set(response.json()) == _run_columns(db_path)


def test_get_run_log_returns_tail_and_404(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))

    with TestClient(app) as client:
        run_id = _seeded_run_id(db_path)
        log_path = tmp_path / "runs" / f"{run_id}.log"
        log_path.parent.mkdir()
        payload = (b"a" * 1_048_576) + b"tail"
        log_path.write_bytes(payload)

        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE run SET log_path = ? WHERE id = ?", (str(log_path), run_id)
            )
            connection.commit()

        response = client.get(f"/api/runs/{run_id}/log")
        missing = client.get(f"/api/runs/{run_id + 1}/log")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert len(response.content) <= 1_048_576
    assert response.content == payload[-1_048_576:]
    assert response.content.endswith(b"tail")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "log_not_found"}
