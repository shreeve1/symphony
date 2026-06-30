from __future__ import annotations

import asyncio
import os
import subprocess
import threading
import time
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

    # Stub title generation so tests never call a live pi binary.
    from web.api.title_generator import generate_issue_title as _real_generate

    def _fake_title(description: str, *, run_func=None) -> str:
        return _real_generate(description, run_func=lambda *a, **kw: _FakePiResult())

    monkeypatch.setattr(main._title_generator, "generate_issue_title", _fake_title)

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


class _FakePiResult:
    returncode = 1
    stdout = ""


def test_create_minimal_issue_applies_server_defaults(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/symphony/issues",
        json={"description": "smoke", "preferred_skill": "/diagnose"},
    )
    assert response.status_code == 201
    body = response.json()

    assert isinstance(body["id"], int)
    assert body["binding_name"] == "symphony"
    assert body["title"] == "smoke"  # server-generated from description
    assert body["description"] == "smoke"
    assert body["preferred_skill"] == "/diagnose"
    # Server-side defaults (#014 spec).
    assert body["state"] == "todo"
    assert body["reasoning_effort"] == "high"
    assert body["worktree_active"] is False
    assert body["auto_land"] is False
    assert body["hold"] is False
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
            "description": "full payload test description",
            "priority": "urgent",
            "preferred_skill": "tdd",
            "preferred_agent": "claude",
            "preferred_model": "claude-fable-5",
            "reasoning_effort": "low",
            "worktree_active": True,
            "auto_land": True,
            "hold": True,
            "base_branch": "develop",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["description"] == "full payload test description"
    assert body["priority"] == "urgent"
    assert body["preferred_skill"] == "tdd"
    assert body["preferred_agent"] == "claude"
    assert body["preferred_model"] == "claude-fable-5"
    assert body["reasoning_effort"] == "low"
    assert body["worktree_active"] is True
    assert body["auto_land"] is True
    assert body["hold"] is True
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
        json={"description": f"effort {effort}", "reasoning_effort": effort},
    )
    assert response.status_code == 201
    assert response.json()["reasoning_effort"] == effort


def test_created_issue_appears_in_binding_list(client: TestClient) -> None:
    created = client.post(
        "/api/bindings/symphony/issues", json={"description": "listed"}
    ).json()
    listed = client.get("/api/bindings/symphony/issues").json()
    assert created["id"] in [issue["id"] for issue in listed]
    # Freshly created issue has the newest updated_at, so it sorts first.
    assert listed[0]["id"] == created["id"]


def test_create_dependency_fields_round_trip(client: TestClient) -> None:
    parent = client.post(
        "/api/bindings/symphony/issues", json={"description": "parent"}
    ).json()
    response = client.post(
        "/api/bindings/symphony/issues",
        json={
            "description": "child",
            "blocked_by": [parent["id"]],
            "locks": ["web-api"],
        },
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


def test_create_missing_description_returns_422(client: TestClient) -> None:
    response = client.post("/api/bindings/symphony/issues", json={})
    assert response.status_code == 422


def test_create_title_in_body_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/symphony/issues",
        json={"description": "something", "title": "overridden"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail[0]["type"] == "extra_forbidden"
    assert detail[0]["loc"] == ["title"]


def test_create_unknown_binding_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/no-such-binding/issues", json={"description": "smoke"}
    )
    assert response.status_code == 404


def test_create_unknown_binding_beats_body_validation(client: TestClient) -> None:
    # Pins the precedence: binding existence is checked before the body is
    # validated (consistent with PATCH's resource-lookup-first ordering), so
    # an invalid body against an unknown binding is 404, not 400/422.
    response = client.post(
        "/api/bindings/no-such-binding/issues",
        json={"description": "smoke", "state": "done"},
    )
    assert response.status_code == 404


def test_create_base_branch_follows_bindings_yml(
    client: TestClient, monkeypatch, tmp_path
) -> None:
    custom = tmp_path / "bindings.yml"
    custom.write_text("bindings:\n  - name: symphony\n    base_branch: develop\n")
    monkeypatch.setattr(main, "BINDINGS_PATH", custom)
    response = client.post(
        "/api/bindings/symphony/issues", json={"description": "branched"}
    )
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
    response = client.post(
        "/api/bindings/symphony/issues", json={"description": "fallback"}
    )
    assert response.status_code == 201
    assert response.json()["base_branch"] == "main"


def test_create_with_state_field_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/symphony/issues", json={"description": "smoke", "state": "done"}
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail[0]["type"] == "extra_forbidden"
    assert detail[0]["loc"] == ["state"]


# (body, expected status) — one validation failure per rule.
FAILURE_CASES = [
    ({"description": ""}, 422),
    ({"description": None}, 422),
    ({"description": 7}, 422),
    ({"description": "ok", "priority": "critical"}, 422),
    ({"description": "ok", "preferred_skill": "no-such-skill"}, 422),
    ({"description": "ok", "preferred_agent": 42}, 422),
    ({"description": "ok", "preferred_model": []}, 422),
    ({"description": "ok", "worktree_active": "maybe"}, 422),
    ({"description": "ok", "auto_land": "maybe"}, 422),
    ({"description": "ok", "reasoning_effort": "max"}, 422),
    ({"description": "ok", "reasoning_effort": None}, 422),
    ({"description": "ok", "base_branch": 7}, 422),
    ({"description": "ok", "flavor": "grape"}, 400),  # unknown field
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
        json={"description": "custom model", "preferred_model": "unlisted-model"},
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


def test_create_allows_worktree_active_for_remote_binding(
    client: TestClient, monkeypatch
) -> None:
    # Remote coding bindings use SSH-created per-issue worktrees too.
    from web.api.tests.conftest import REMOTE_BINDING_ENTRY, REMOTE_BINDING_NAME

    with main.connect(Path(os.environ["PODIUM_DB_PATH"])) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO binding(name) VALUES (?)", (REMOTE_BINDING_NAME,)
        )
        connection.commit()
    monkeypatch.setattr(main, "_bindings_override", [REMOTE_BINDING_ENTRY])
    response = client.post(
        f"/api/bindings/{REMOTE_BINDING_NAME}/issues",
        json={"description": "remote", "worktree_active": True},
    )
    assert response.status_code == 201
    assert response.json()["worktree_active"] is True


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


def test_create_pi_failure_falls_back_to_first_line(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/symphony/issues",
        json={
            "description": "line one\nline two\nline three",
            "preferred_skill": "/diagnose",
        },
    )
    assert response.status_code == 201
    body = response.json()
    # pi isn't available in tests; fallback = first non-blank line
    assert body["title"] == "line one"
    assert body["description"] == "line one\nline two\nline three"


def test_create_fallback_truncates_long_first_line(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/symphony/issues",
        json={
            "description": "this is a very long first line that exceeds eighty characters by quite a margin and should be truncated at a word boundary",
            "preferred_skill": "/diagnose",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert len(body["title"]) <= 80
    # Must be a prefix of the first line.
    assert "this is a very long first line that exceeds eighty characters by quite a margin and should be truncated at a word boundary".startswith(
        body["title"]
    )


def test_patch_can_still_rename_title(client: TestClient) -> None:
    created = client.post(
        "/api/bindings/symphony/issues",
        json={"description": "original"},
    ).json()
    response = client.patch(f"/api/issues/{created['id']}", json={"title": "renamed"})
    assert response.status_code == 200
    assert response.json()["title"] == "renamed"


class TestGenerateIssueTitle:
    def test_returns_pi_output_when_successful(self) -> None:
        from web.api.title_generator import generate_issue_title

        def fake_run(cmd, **kwargs):
            class R:
                returncode = 0
                stdout = "generated title from pi"

            return R()

        assert (
            generate_issue_title("desc", run_func=fake_run) == "generated title from pi"
        )

    def test_falls_back_on_nonzero_exit(self) -> None:
        from web.api.title_generator import generate_issue_title

        def fake_run(cmd, **kwargs):
            class R:
                returncode = 1
                stdout = "stuff"

            return R()

        assert (
            generate_issue_title("first line\nsecond line", run_func=fake_run)
            == "first line"
        )

    def test_falls_back_on_timeout(self) -> None:
        from web.api.title_generator import generate_issue_title

        def fake_run(cmd, **kwargs):
            raise TimeoutError()

        assert generate_issue_title("first line", run_func=fake_run) == "first line"

    def test_uses_realistic_timeout(self) -> None:
        from web.api.title_generator import generate_issue_title

        def fake_run(cmd, **kwargs):
            # A one-shot pi call empirically takes ~20-25s; the timeout must be
            # a realistic ceiling, not the 1s band-aid that always fell back.
            assert kwargs["timeout"] >= 15

            class R:
                returncode = 0
                stdout = "fast title"

            return R()

        assert generate_issue_title("desc", run_func=fake_run) == "fast title"

    def test_falls_back_on_empty_stdout(self) -> None:
        from web.api.title_generator import generate_issue_title

        def fake_run(cmd, **kwargs):
            class R:
                returncode = 0
                stdout = "  \n"

            return R()

        assert generate_issue_title("first line", run_func=fake_run) == "first line"

    def test_normalises_quoted_output(self) -> None:
        from web.api.title_generator import generate_issue_title

        def fake_run(cmd, **kwargs):
            class R:
                returncode = 0
                stdout = '"quoted title"'

            return R()

        assert generate_issue_title("desc", run_func=fake_run) == "quoted title"

    def test_normalises_markdown_heading(self) -> None:
        from web.api.title_generator import generate_issue_title

        def fake_run(cmd, **kwargs):
            class R:
                returncode = 0
                stdout = "## markdown title"

            return R()

        assert generate_issue_title("desc", run_func=fake_run) == "markdown title"

    def test_truncates_long_output(self) -> None:
        from web.api.title_generator import generate_issue_title

        # Title with spaces: word boundary truncation cuts at last space within 80.
        long_title = "a " + "b " * 50  # ~100 chars with spaces

        def fake_run(cmd, **kwargs):
            class R:
                returncode = 0
                stdout = long_title

            return R()

        result = generate_issue_title("desc", run_func=fake_run)
        assert len(result) <= 80
        assert result.endswith("b")

    def test_truncates_long_output_no_spaces(self) -> None:
        from web.api.title_generator import generate_issue_title

        # No spaces: truncation returns first 80 chars unchanged.
        long_title = "x" * 100

        def fake_run(cmd, **kwargs):
            class R:
                returncode = 0
                stdout = long_title

            return R()

        result = generate_issue_title("desc", run_func=fake_run)
        assert result == "x" * 80


def _run_loop_briefly(fn):
    """Run fn (which schedules onto an asyncio loop) on a throwaway loop."""
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    try:
        fn(loop)
        for _ in range(200):
            time.sleep(0.01)
    finally:
        loop.call_soon_threadsafe(loop.stop)


def test_regenerate_title_updates_row_and_pushes(client, monkeypatch):
    # Create inserts the instant fallback title (first description line).
    created = client.post(
        "/api/bindings/symphony/issues", json={"description": "first line\nmore"}
    ).json()
    issue_id = created["id"]
    assert created["title"] == "first line"

    # Background pi generation yields a distinct title.
    monkeypatch.setattr(
        main._title_generator, "generate_issue_title", lambda desc, **kw: "A Good Title"
    )
    seen = []

    async def fake_publish(msg):
        seen.append(msg)

    monkeypatch.setattr(main.websocket_hub, "publish", fake_publish)

    _run_loop_briefly(
        lambda loop: main._regenerate_title(
            main.resolve_db_path(), issue_id, "first line\nmore", "first line", loop
        )
    )

    with main.connect(main.resolve_db_path()) as conn:
        row = conn.execute(
            "SELECT title FROM issue WHERE id = ?", (issue_id,)
        ).fetchone()
    assert row["title"] == "A Good Title"
    assert seen and seen[0]["type"] == "issue.updated" and seen[0]["id"] == issue_id


def test_regenerate_title_noop_when_title_matches_fallback(client, monkeypatch):
    created = client.post(
        "/api/bindings/symphony/issues", json={"description": "first line\nmore"}
    ).json()
    issue_id = created["id"]

    # pi returns the same string as the fallback already stored -> no write.
    monkeypatch.setattr(
        main._title_generator, "generate_issue_title", lambda desc, **kw: "first line"
    )
    seen = []

    async def fake_publish(msg):
        seen.append(msg)

    monkeypatch.setattr(main.websocket_hub, "publish", fake_publish)

    _run_loop_briefly(
        lambda loop: main._regenerate_title(
            main.resolve_db_path(), issue_id, "first line\nmore", "first line", loop
        )
    )

    assert seen == []
    assert created["title"] == "first line"
