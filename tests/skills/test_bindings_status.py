from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

skill_migration = cast(Any, import_module("skill_migration"))
podium_bindings_status = skill_migration.podium_bindings_status
web_conftest = cast(Any, import_module("web.api.tests.conftest"))
login = web_conftest.login
main = cast(Any, import_module("web.api.main"))
app = main.app


SKILL_PATH = Path(".claude/skills/symphony-bindings-status/SKILL.md")


def test_bindings_status_reads_podium_bindings_and_issues(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setenv("PODIUM_PASSWORD_HASH", web_conftest.TEST_PASSWORD_HASH)
    monkeypatch.setenv("PODIUM_SESSION_SECRET", web_conftest.TEST_SESSION_SECRET)
    main._auth_config = None

    with TestClient(app) as client:
        login(client)
        rows = podium_bindings_status(client)

    by_name = {row["name"]: row for row in rows}
    assert "symphony" in by_name
    assert by_name["symphony"]["open_issue_count"] >= 1
    assert by_name["symphony"]["latest_issue_state"] in {
        "todo",
        "running",
        "in_review",
        "blocked",
        "done",
    }


def test_bindings_status_skill_reads_podium_not_plane() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "GET /api/bindings" in text
    assert "GET /api/bindings/{name}/issues" in text
    assert "No Plane API calls" in text
    assert "PLANE_API_URL" not in text
    assert "api/v1/workspaces" not in text
