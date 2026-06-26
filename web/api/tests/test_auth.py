from __future__ import annotations

import time
from importlib import import_module
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

TEST_PASSWORD = cast(Any, import_module("web.api.tests.conftest")).TEST_PASSWORD

auth = cast(Any, import_module("web.api.auth"))
main = import_module("web.api.main")
app = cast(Any, main.app)


def test_correct_password_sets_session_cookie(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PODIUM_DB_PATH", str(tmp_path / "podium.db"))

    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"password": TEST_PASSWORD})
        whoami = client.get("/api/auth/whoami")

    assert response.status_code == 200
    assert response.json() == {"authenticated": True}
    assert "podium_session" in response.cookies
    assert whoami.status_code == 200


def test_wrong_password_returns_401_after_250ms(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PODIUM_DB_PATH", str(tmp_path / "podium.db"))

    with TestClient(app) as client:
        start = time.perf_counter()
        response = client.post("/api/auth/login", json={"password": "wrong"})
        elapsed = time.perf_counter() - start

    assert response.status_code == 401
    assert elapsed >= 0.25


def test_missing_cookie_on_protected_route_returns_401(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PODIUM_DB_PATH", str(tmp_path / "podium.db"))

    with TestClient(app) as client:
        response = client.get("/api/bindings")

    assert response.status_code == 401


def test_logout_clears_cookie(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PODIUM_DB_PATH", str(tmp_path / "podium.db"))

    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"password": TEST_PASSWORD})
        logout = client.post("/api/auth/logout")
        whoami = client.get("/api/auth/whoami")

    assert login.status_code == 200
    assert logout.status_code == 200
    assert "podium_session" in logout.headers["set-cookie"]
    assert whoami.status_code == 401


def test_rate_limit_after_five_failed_attempts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PODIUM_DB_PATH", str(tmp_path / "podium.db"))

    with TestClient(app) as client:
        failures = [
            client.post("/api/auth/login", json={"password": "wrong"}) for _ in range(5)
        ]
        limited = client.post("/api/auth/login", json={"password": "wrong"})

    assert [response.status_code for response in failures] == [401] * 5
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"


def test_session_secret_unset_fails_startup(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PODIUM_DB_PATH", str(tmp_path / "podium.db"))
    monkeypatch.delenv("PODIUM_SESSION_SECRET", raising=False)
    monkeypatch.setattr(auth, "load_dotenv", lambda path=auth.REPO_ROOT / ".env": None)

    with pytest.raises(RuntimeError, match="PODIUM_SESSION_SECRET"), TestClient(app):
        pass


def test_health_is_public_when_unauthenticated(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PODIUM_DB_PATH", str(tmp_path / "podium.db"))

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200


def test_bearer_token_authenticates_without_cookie(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PODIUM_DB_PATH", str(tmp_path / "podium.db"))
    monkeypatch.setenv("PODIUM_API_TOKEN", "service-token-xyz")

    with TestClient(app) as client:
        response = client.get(
            "/api/bindings",
            headers={"Authorization": "Bearer service-token-xyz"},
        )

    assert response.status_code == 200


def test_wrong_bearer_token_returns_401(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PODIUM_DB_PATH", str(tmp_path / "podium.db"))
    monkeypatch.setenv("PODIUM_API_TOKEN", "service-token-xyz")

    with TestClient(app) as client:
        response = client.get(
            "/api/bindings",
            headers={"Authorization": "Bearer wrong-token"},
        )

    assert response.status_code == 401


def test_bearer_token_ignored_when_unset(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PODIUM_DB_PATH", str(tmp_path / "podium.db"))
    monkeypatch.delenv("PODIUM_API_TOKEN", raising=False)
    monkeypatch.setattr(auth, "load_dotenv", lambda path=auth.REPO_ROOT / ".env": None)

    with TestClient(app) as client:
        response = client.get(
            "/api/bindings",
            headers={"Authorization": "Bearer service-token-xyz"},
        )

    assert response.status_code == 401


def test_bearer_authenticates_mutating_endpoint(monkeypatch, tmp_path) -> None:
    # The service token authorizes mutating routes too (not just GET) — the
    # security-relevant capability. PATCH a nonexistent issue: a 401 would mean
    # auth failed; 404 means auth passed and the route ran.
    monkeypatch.setenv("PODIUM_DB_PATH", str(tmp_path / "podium.db"))
    monkeypatch.setenv("PODIUM_API_TOKEN", "service-token-xyz")

    with TestClient(app) as client:
        response = client.patch(
            "/api/issues/999999",
            json={"description": "x"},
            headers={"Authorization": "Bearer service-token-xyz"},
        )

    assert response.status_code != 401


@pytest.mark.parametrize(
    "header,expected",
    [
        ("Bearer tok", True),
        ("bearer tok", True),  # scheme is case-insensitive
        ("  Bearer   tok  ", True),  # surrounding whitespace tolerated
        ("Bearer wrong", False),
        ("Bearer", False),  # scheme only, no token
        ("Bearer ", False),  # empty token
        ("Basic tok", False),  # wrong scheme
        ("tok", False),  # no scheme
        ("", False),
        (None, False),
    ],
)
def test_verify_bearer_token_header_parsing(header, expected) -> None:
    config = auth.AuthConfig(
        password_hash="unused", session_secret="unused", api_token="tok"
    )
    assert auth.verify_bearer_token(header, config) is expected


def test_verify_bearer_token_false_when_no_token_configured() -> None:
    config = auth.AuthConfig(password_hash="unused", session_secret="unused")
    assert auth.verify_bearer_token("Bearer anything", config) is False
