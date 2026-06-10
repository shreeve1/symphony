from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from importlib import import_module
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

main = import_module("web.api.main")
app = cast(Any, main.app)


@pytest.fixture()
def client(monkeypatch, tmp_path) -> Iterator[TestClient]:
    monkeypatch.setenv("PODIUM_DB_PATH", str(tmp_path / "podium.db"))
    with TestClient(app) as test_client:
        yield test_client


def test_create_minimal_issue_applies_server_defaults(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/trading/issues",
        json={"title": "smoke", "preferred_skill": "/diagnose"},
    )
    assert response.status_code == 201
    body = response.json()

    assert isinstance(body["id"], int)
    assert body["binding_name"] == "trading"
    assert body["title"] == "smoke"
    assert body["preferred_skill"] == "/diagnose"
    # Server-side defaults (#014 spec).
    assert body["state"] == "todo"
    assert body["reasoning_effort"] == "high"
    assert body["worktree_active"] is False
    assert body["base_branch"] == "main"  # trading base_branch in bindings.yml
    assert body["created_at"] is not None
    assert body["updated_at"] is not None

    # Round-trip through SQLite via a fresh read.
    fetched = client.get(f"/api/issues/{body['id']}").json()
    assert fetched == body


def test_create_with_all_optional_fields(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/homelab/issues",
        json={
            "title": "full payload",
            "description": "All optional fields set.",
            "priority": "urgent",
            "preferred_skill": "tdd",
            "preferred_agent": "claude",
            "preferred_model": "claude-fable-5",
            "reasoning_effort": "low",
            "worktree_active": True,
            "base_branch": "develop",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["description"] == "All optional fields set."
    assert body["priority"] == "urgent"
    assert body["preferred_skill"] == "tdd"
    assert body["preferred_agent"] == "claude"
    assert body["preferred_model"] == "claude-fable-5"
    assert body["reasoning_effort"] == "low"
    assert body["worktree_active"] is True
    # Explicit base_branch wins over the bindings.yml default.
    assert body["base_branch"] == "develop"


def test_created_issue_appears_in_binding_list(client: TestClient) -> None:
    created = client.post(
        "/api/bindings/trading/issues", json={"title": "listed"}
    ).json()
    listed = client.get("/api/bindings/trading/issues").json()
    assert created["id"] in [issue["id"] for issue in listed]
    # Freshly created issue has the newest updated_at, so it sorts first.
    assert listed[0]["id"] == created["id"]


def test_create_missing_title_returns_422(client: TestClient) -> None:
    response = client.post("/api/bindings/trading/issues", json={})
    assert response.status_code == 422


def test_create_unknown_binding_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/no-such-binding/issues", json={"title": "smoke"}
    )
    assert response.status_code == 404


def test_create_unknown_binding_beats_body_validation(client: TestClient) -> None:
    # Pins the precedence: binding existence is checked before the body is
    # validated (consistent with PATCH's resource-lookup-first ordering), so
    # an invalid body against an unknown binding is 404, not 400/422.
    response = client.post(
        "/api/bindings/no-such-binding/issues",
        json={"title": "smoke", "state": "done"},
    )
    assert response.status_code == 404


def test_create_base_branch_follows_bindings_yml(
    client: TestClient, monkeypatch, tmp_path
) -> None:
    custom = tmp_path / "bindings.yml"
    custom.write_text("bindings:\n  - name: trading\n    base_branch: develop\n")
    monkeypatch.setattr(main, "BINDINGS_PATH", custom)
    response = client.post("/api/bindings/trading/issues", json={"title": "branched"})
    assert response.status_code == 201
    assert response.json()["base_branch"] == "develop"


@pytest.mark.parametrize("content", [None, ": not [ yaml"])
def test_create_falls_back_to_main_when_bindings_yml_unreadable(
    client: TestClient, monkeypatch, tmp_path, content: str | None
) -> None:
    # None = file missing entirely; string = malformed YAML. Neither may 500.
    broken = tmp_path / "bindings.yml"
    if content is not None:
        broken.write_text(content)
    monkeypatch.setattr(main, "BINDINGS_PATH", broken)
    response = client.post("/api/bindings/trading/issues", json={"title": "fallback"})
    assert response.status_code == 201
    assert response.json()["base_branch"] == "main"


def test_create_with_state_field_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/trading/issues", json={"title": "smoke", "state": "done"}
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail[0]["type"] == "extra_forbidden"
    assert detail[0]["loc"] == ["state"]


# (body, expected status) — one validation failure per rule.
FAILURE_CASES = [
    ({"title": ""}, 422),
    ({"title": None}, 422),
    ({"title": 7}, 422),
    ({"title": "ok", "description": 123}, 422),
    ({"title": "ok", "priority": "critical"}, 422),
    ({"title": "ok", "preferred_skill": "no-such-skill"}, 422),
    ({"title": "ok", "preferred_agent": 42}, 422),
    ({"title": "ok", "preferred_model": []}, 422),
    ({"title": "ok", "worktree_active": "maybe"}, 422),
    ({"title": "ok", "reasoning_effort": "max"}, 422),
    ({"title": "ok", "reasoning_effort": None}, 422),
    ({"title": "ok", "base_branch": 7}, 422),
    ({"title": "ok", "flavor": "grape"}, 400),  # unknown field
]


def test_options_returns_agents_models_and_branches(
    client: TestClient, monkeypatch, tmp_path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True)
    (repo / "f").write_text("x")
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "init"],
        check=True,
        env={**os.environ, **env},
    )
    subprocess.run(["git", "-C", str(repo), "branch", "develop"], check=True)

    custom = tmp_path / "bindings.yml"
    custom.write_text(
        f"bindings:\n  - name: trading\n    repo_path: {repo}\n"
    )
    monkeypatch.setattr(main, "BINDINGS_PATH", custom)

    response = client.get("/api/bindings/trading/options")
    assert response.status_code == 200
    body = response.json()
    assert body["agents"] == ["pi", "claude"]
    assert "claude-fable-5" in body["models"]
    assert body["branches"] == ["develop", "main"]


def test_options_unknown_binding_returns_404(client: TestClient) -> None:
    assert client.get("/api/bindings/no-such-binding/options").status_code == 404


def test_options_branches_degrade_to_empty_on_bad_repo(
    client: TestClient, monkeypatch, tmp_path
) -> None:
    # repo_path that exists but is not a git repo: branches must be [] not 500.
    custom = tmp_path / "bindings.yml"
    custom.write_text(
        f"bindings:\n  - name: trading\n    repo_path: {tmp_path}\n"
    )
    monkeypatch.setattr(main, "BINDINGS_PATH", custom)
    response = client.get("/api/bindings/trading/options")
    assert response.status_code == 200
    assert response.json()["branches"] == []


@pytest.mark.parametrize(("body", "expected_status"), FAILURE_CASES)
def test_create_rejects_invalid_body(
    client: TestClient, body: dict[str, Any], expected_status: int
) -> None:
    before = client.get("/api/bindings/trading/issues").json()

    response = client.post("/api/bindings/trading/issues", json=body)
    assert response.status_code == expected_status

    # Rejected POST must not insert anything.
    after = client.get("/api/bindings/trading/issues").json()
    assert after == before
