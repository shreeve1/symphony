from __future__ import annotations

import os
import subprocess
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
        with main.connect(db_path) as connection:
            connection.executemany(
                "INSERT INTO skill(name, description, source) VALUES (?, ?, '')",
                [
                    ("/diagnose", "Diagnose fixture skill"),
                    ("tdd", "TDD fixture skill"),
                ],
            )
            connection.commit()
        yield test_client


def test_create_minimal_issue_applies_server_defaults(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/symphony/issues",
        json={"title": "smoke", "preferred_skill": "/diagnose"},
    )
    assert response.status_code == 201
    body = response.json()

    assert isinstance(body["id"], int)
    assert body["binding_name"] == "symphony"
    assert body["title"] == "smoke"
    assert body["preferred_skill"] == "/diagnose"
    # Server-side defaults (#014 spec).
    assert body["state"] == "todo"
    assert body["reasoning_effort"] == "high"
    assert body["worktree_active"] is False
    assert body["auto_land"] is False
    assert body["base_branch"] == "main"  # symphony base_branch in bindings.yml
    assert body["blocked_by"] == []
    assert body["locks"] == []
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
            "auto_land": True,
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
    assert body["auto_land"] is True
    # Explicit base_branch wins over the bindings.yml default.
    assert body["base_branch"] == "develop"


@pytest.mark.parametrize(
    "effort", ["none", "minimal", "low", "medium", "high", "xhigh"]
)
def test_create_accepts_model_specific_efforts(client: TestClient, effort: str) -> None:
    # The API accepts the full effort vocabulary across models (gpt-5.5 added
    # `none`/`xhigh`); per-model validity is enforced at the dispatch gate.
    response = client.post(
        "/api/bindings/homelab/issues",
        json={"title": f"effort {effort}", "reasoning_effort": effort},
    )
    assert response.status_code == 201
    assert response.json()["reasoning_effort"] == effort


def test_created_issue_appears_in_binding_list(client: TestClient) -> None:
    created = client.post(
        "/api/bindings/symphony/issues", json={"title": "listed"}
    ).json()
    listed = client.get("/api/bindings/symphony/issues").json()
    assert created["id"] in [issue["id"] for issue in listed]
    # Freshly created issue has the newest updated_at, so it sorts first.
    assert listed[0]["id"] == created["id"]


def test_create_dependency_fields_round_trip(client: TestClient) -> None:
    parent = client.post(
        "/api/bindings/symphony/issues", json={"title": "parent"}
    ).json()
    response = client.post(
        "/api/bindings/symphony/issues",
        json={"title": "child", "blocked_by": [parent["id"]], "locks": ["web-api"]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["blocked_by"] == [parent["id"]]
    assert body["locks"] == ["web-api"]

    fetched = client.get(f"/api/issues/{body['id']}").json()
    listed = client.get("/api/bindings/symphony/issues").json()
    assert fetched["blocked_by"] == [parent["id"]]
    assert fetched["locks"] == ["web-api"]
    assert listed[0]["blocked_by"] == [parent["id"]]
    assert listed[0]["locks"] == ["web-api"]


def test_create_missing_title_returns_422(client: TestClient) -> None:
    response = client.post("/api/bindings/symphony/issues", json={})
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
    custom.write_text("bindings:\n  - name: symphony\n    base_branch: develop\n")
    monkeypatch.setattr(main, "BINDINGS_PATH", custom)
    response = client.post("/api/bindings/symphony/issues", json={"title": "branched"})
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
    response = client.post("/api/bindings/symphony/issues", json={"title": "fallback"})
    assert response.status_code == 201
    assert response.json()["base_branch"] == "main"


def test_create_with_state_field_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/symphony/issues", json={"title": "smoke", "state": "done"}
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
    ({"title": "ok", "auto_land": "maybe"}, 422),
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
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "init"],
        check=True,
        env={**os.environ, **env},
    )
    subprocess.run(["git", "-C", str(repo), "branch", "develop"], check=True)

    custom = tmp_path / "bindings.yml"
    custom.write_text(f"bindings:\n  - name: symphony\n    repo_path: {repo}\n")
    monkeypatch.setattr(main, "BINDINGS_PATH", custom)
    models = tmp_path / "models.yml"
    models.write_text(
        "models:\n"
        "  - id: claude-fable-5\n"
        "    agent: claude\n"
        "  - id: glm-5.1:high\n"
        "    agent: pi\n"
        "    provider: zai\n"
        "    default: true\n"
    )
    monkeypatch.setattr(main, "MODELS_PATH", models)

    response = client.get("/api/bindings/symphony/options")
    assert response.status_code == 200
    body = response.json()
    assert body["agents"] == ["pi", "claude"]
    assert body["models"] == [
        {"id": "claude-fable-5", "agent": "claude"},
        {"id": "glm-5.1:high", "agent": "pi", "provider": "zai", "default": True},
    ]
    assert body["branches"] == ["develop", "main"]


def test_models_validator_rejects_invalid_catalogs() -> None:
    assert main._validate_models(
        {"models": [{"id": "claude-fable-5", "agent": "claude", "default": True}]}
    ) == [{"id": "claude-fable-5", "agent": "claude", "default": True}]

    with pytest.raises(
        ValueError, match="multiple default: true entries for agent `claude`"
    ):
        main._validate_models(
            {
                "models": [
                    {"id": "claude-fable-5", "agent": "claude", "default": True},
                    {"id": "claude-opus-4-8", "agent": "claude", "default": True},
                ]
            }
        )
    with pytest.raises(ValueError, match="provider is required for pi models"):
        main._validate_models(
            {"models": [{"id": "glm-5.1:high", "agent": "pi", "default": True}]}
        )
    with pytest.raises(ValueError, match="id is required"):
        main._validate_models({"models": [{"agent": "claude"}]})
    with pytest.raises(ValueError, match="agent must be one of"):
        main._validate_models({"models": [{"id": "bad", "agent": "bad"}]})
    with pytest.raises(ValueError, match="duplicate model entry"):
        main._validate_models(
            {
                "models": [
                    {"id": "claude-fable-5", "agent": "claude"},
                    {"id": "claude-fable-5", "agent": "claude"},
                ]
            }
        )


@pytest.mark.parametrize(
    "content", [None, ": not [ yaml", "models:\n  - id: x\n    agent: bad\n"]
)
def test_options_models_degrade_to_empty_on_bad_catalog(
    client: TestClient, monkeypatch, tmp_path, content: str | None
) -> None:
    catalog = tmp_path / "models.yml"
    if content is not None:
        catalog.write_text(content)
    monkeypatch.setattr(main, "MODELS_PATH", catalog)

    response = client.get("/api/bindings/symphony/options")
    assert response.status_code == 200
    assert response.json()["models"] == []


def test_create_accepts_free_text_model_not_in_catalog(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/symphony/issues",
        json={"title": "custom model", "preferred_model": "unlisted-model"},
    )
    assert response.status_code == 201
    assert response.json()["preferred_model"] == "unlisted-model"


def test_options_unknown_binding_returns_404(client: TestClient) -> None:
    assert client.get("/api/bindings/no-such-binding/options").status_code == 404


def test_options_branches_degrade_to_empty_on_bad_repo(
    client: TestClient, monkeypatch, tmp_path
) -> None:
    # repo_path that exists but is not a git repo: branches must be [] not 500.
    custom = tmp_path / "bindings.yml"
    custom.write_text(f"bindings:\n  - name: symphony\n    repo_path: {tmp_path}\n")
    monkeypatch.setattr(main, "BINDINGS_PATH", custom)
    response = client.get("/api/bindings/symphony/options")
    assert response.status_code == 200
    assert response.json()["branches"] == []


def test_create_coerces_worktree_active_off_for_remote_binding(
    client: TestClient, monkeypatch
) -> None:
    # Remote bindings (ADR-0012) defer worktrees: worktree_active is forced
    # False at create even when the client asks for it.
    from web.api.tests.conftest import REMOTE_BINDING_ENTRY, REMOTE_BINDING_NAME

    with main.connect(Path(os.environ["PODIUM_DB_PATH"])) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO binding(name) VALUES (?)", (REMOTE_BINDING_NAME,)
        )
        connection.commit()
    monkeypatch.setattr(main, "_bindings_override", [REMOTE_BINDING_ENTRY])
    response = client.post(
        f"/api/bindings/{REMOTE_BINDING_NAME}/issues",
        json={"title": "remote", "worktree_active": True},
    )
    assert response.status_code == 201
    assert response.json()["worktree_active"] is False


@pytest.mark.parametrize(("body", "expected_status"), FAILURE_CASES)
def test_create_rejects_invalid_body(
    client: TestClient, body: dict[str, Any], expected_status: int
) -> None:
    before = client.get("/api/bindings/symphony/issues").json()

    response = client.post("/api/bindings/symphony/issues", json=body)
    assert response.status_code == expected_status

    # Rejected POST must not insert anything.
    after = client.get("/api/bindings/symphony/issues").json()
    assert after == before
