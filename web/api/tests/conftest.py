from __future__ import annotations

from collections.abc import Iterator
from importlib import import_module
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

TEST_PASSWORD = "secret"
TEST_PASSWORD_HASH = "$2b$12$ZjUmIMBDipXIftuigS2s0O3SSJzKwkSHWsrHmauOcytbDU.K3e1k2"
TEST_SESSION_SECRET = "test-session-secret"


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PODIUM_PASSWORD_HASH", TEST_PASSWORD_HASH)
    monkeypatch.setenv("PODIUM_SESSION_SECRET", TEST_SESSION_SECRET)
    auth = cast(Any, import_module("web.api.auth"))
    auth.reset_rate_limits()
    yield
    auth.reset_rate_limits()


def login(client: TestClient, password: str = TEST_PASSWORD) -> None:
    response = client.post("/api/auth/login", json={"password": password})
    assert response.status_code == 200
