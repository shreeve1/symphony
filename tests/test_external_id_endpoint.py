"""Endpoint coverage for the issue.external_id dedup key (ADR-0015 §3, Wave B).

Exercises create-persists, ?external_id= filter, and the duplicate->409
contract against a fresh SCHEMA_SQL database (which now carries the column +
global-unique index added in migration 0009).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.api.schema import SCHEMA_SQL


@pytest.fixture()
def client(tmp_path: Path, monkeypatch) -> TestClient:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT INTO binding(name, display_name) VALUES ('homelab-patrol', 'Patrol')"
        )
        conn.commit()

    from web.api import main as web_main

    # Stub pi for title generation: all title generation in tests falls back
    # to the first line of the description (no live pi binary needed).
    from web.api.title_generator import generate_issue_title as _real_generate

    class _FakePiResult:
        returncode = 1
        stdout = ""

    def _fake_title(description: str, *, run_func=None) -> str:
        return _real_generate(description, run_func=lambda *a, **kw: _FakePiResult())

    monkeypatch.setattr(web_main._title_generator, "generate_issue_title", _fake_title)

    # Bypass the cookie-session auth middleware; this suite tests the issue
    # endpoints, not auth. The middleware calls module-level verify_session.
    monkeypatch.setattr(web_main, "verify_session", lambda *a, **k: True)
    monkeypatch.setattr(web_main, "_get_auth_config", lambda: None)

    return TestClient(web_main.app)


def _create(client: TestClient, **body):
    body.setdefault("description", "patrol finding")
    if "title" in body:
        body["description"] = body.pop("title")
    resp = client.post("/api/bindings/homelab-patrol/issues", json=body)
    return resp


def test_create_persists_external_id(client: TestClient):
    resp = _create(client, external_id="homelab-patrol-abc12345")
    assert resp.status_code == 201
    assert resp.json()["external_id"] == "homelab-patrol-abc12345"


def test_create_without_external_id_is_null(client: TestClient):
    resp = _create(client)
    assert resp.status_code == 201
    assert resp.json()["external_id"] is None


def test_external_id_filter_returns_match_and_empty(client: TestClient):
    _create(client, external_id="homelab-patrol-aaa", title="a")
    _create(client, external_id="homelab-patrol-bbb", title="b")

    match = client.get(
        "/api/bindings/homelab-patrol/issues",
        params={"external_id": "homelab-patrol-aaa"},
    )
    assert match.status_code == 200
    rows = match.json()
    assert len(rows) == 1
    assert rows[0]["external_id"] == "homelab-patrol-aaa"
    assert rows[0]["title"] == "a"

    empty = client.get(
        "/api/bindings/homelab-patrol/issues",
        params={"external_id": "homelab-patrol-nope"},
    )
    assert empty.status_code == 200
    assert empty.json() == []


def test_external_id_filter_combines_with_state(client: TestClient):
    _create(client, external_id="homelab-patrol-state", title="x")
    # Created issues are state='todo'. Filter by todo+external_id -> hit.
    hit = client.get(
        "/api/bindings/homelab-patrol/issues",
        params={"state": "todo", "external_id": "homelab-patrol-state"},
    )
    assert hit.status_code == 200 and len(hit.json()) == 1
    # done+external_id -> miss (state filter still applies).
    miss = client.get(
        "/api/bindings/homelab-patrol/issues",
        params={"state": "done", "external_id": "homelab-patrol-state"},
    )
    assert miss.status_code == 200 and miss.json() == []


def test_duplicate_external_id_create_conflicts(client: TestClient):
    first = _create(client, external_id="homelab-patrol-dup")
    assert first.status_code == 201
    second = _create(client, external_id="homelab-patrol-dup")
    assert second.status_code == 409


def test_multiple_null_external_id_coexist(client: TestClient):
    # SQLite treats NULLs as distinct under UNIQUE -> two null-external_id
    # issues both succeed (the global-unique-nullable contract).
    assert _create(client, title="n1").status_code == 201
    assert _create(client, title="n2").status_code == 201


def test_patch_can_set_external_id(client: TestClient):
    created = _create(client).json()
    issue_id = created["id"]
    resp = client.patch(
        f"/api/issues/{issue_id}", json={"external_id": "homelab-patrol-patched"}
    )
    assert resp.status_code == 200
    assert resp.json()["external_id"] == "homelab-patrol-patched"


def test_patch_duplicate_external_id_conflicts(client: TestClient):
    # PATCH to an external_id already held by another issue hits the global
    # UNIQUE index -> 409 (mirrors the create-conflict contract), not a 500.
    _create(client, external_id="homelab-patrol-taken", title="owner")
    other_id = _create(client, title="other").json()["id"]
    resp = client.patch(
        f"/api/issues/{other_id}", json={"external_id": "homelab-patrol-taken"}
    )
    assert resp.status_code == 409
