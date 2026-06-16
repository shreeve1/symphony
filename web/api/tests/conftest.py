from __future__ import annotations

from collections.abc import Iterator
from importlib import import_module
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

main = import_module("web.api.main")
app = cast(Any, main.app)

TEST_PASSWORD = "secret"
TEST_PASSWORD_HASH = "$2b$12$ZjUmIMBDipXIftuigS2s0O3SSJzKwkSHWsrHmauOcytbDU.K3e1k2"
TEST_SESSION_SECRET = "test-session-secret"


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PODIUM_PASSWORD_HASH", TEST_PASSWORD_HASH)
    monkeypatch.setenv("PODIUM_SESSION_SECRET", TEST_SESSION_SECRET)
    auth = cast(Any, import_module("web.api.auth"))
    main = cast(Any, import_module("web.api.main"))
    main._auth_config = None
    auth.reset_rate_limits()
    yield
    main._auth_config = None
    auth.reset_rate_limits()


def login(client: TestClient, password: str = TEST_PASSWORD) -> None:
    response = client.post("/api/auth/login", json={"password": password})
    assert response.status_code == 200


# Remote binding (ADR-0012): type:coding + pi_mode:one-shot + default_agent:pi
# with a truthy `remote:` block. Mirrors the live n8n bindings.yml entry. n8n is
# now a seeded binding, so tests that INSERT this row directly must use
# `INSERT OR IGNORE` to tolerate the pre-seeded row.
REMOTE_BINDING_NAME = "n8n"
REMOTE_BINDING_ENTRY: dict[str, Any] = {
    "name": REMOTE_BINDING_NAME,
    "repo_path": "/home/itadmin/itastack",
    "base_branch": "main",
    "type": "coding",
    "pi_mode": "one-shot",
    "default_agent": "pi",
    "tracker": "podium",
    "remote": {"user": "itadmin", "host": "100.95.224.218"},
}


@pytest.fixture()
def client(monkeypatch, tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    with TestClient(app) as test_client:
        login(test_client)
        with main.connect(db_path) as connection:
            connection.executemany(
                "INSERT INTO skill(name, description, source) VALUES (?, ?, '')",
                [
                    ("blueprint", "Blueprint fixture skill"),
                    ("code-review", "Code review fixture skill"),
                    ("tdd", "TDD fixture skill"),
                ],
            )
            connection.commit()
        yield test_client


@pytest.fixture()
def issue_id(client: TestClient) -> int:
    issues = client.get("/api/bindings/symphony/issues").json()
    return issues[0]["id"]
