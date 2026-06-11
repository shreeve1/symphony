from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

skill_migration = cast(Any, import_module("skill_migration"))
create_podium_smoke_issue = skill_migration.create_podium_smoke_issue
poll_podium_issue_run = skill_migration.poll_podium_issue_run
web_conftest = cast(Any, import_module("web.api.tests.conftest"))
login = web_conftest.login
main = cast(Any, import_module("web.api.main"))
app = main.app


SKILL_PATH = Path(".claude/skills/symphony-binding-smoke/SKILL.md")


def test_binding_smoke_posts_podium_issue_and_polls_run(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setenv("PODIUM_PASSWORD_HASH", web_conftest.TEST_PASSWORD_HASH)
    monkeypatch.setenv("PODIUM_SESSION_SECRET", web_conftest.TEST_SESSION_SECRET)
    main._auth_config = None

    with TestClient(app) as client:
        login(client)
        issue = create_podium_smoke_issue(
            client,
            "trading",
            title="[smoke] 2026-06-11T00:00:00Z Symphony binding verification",
        )

        assert issue["binding_name"] == "trading"
        assert issue["state"] == "todo"
        assert issue["title"].startswith("[smoke]")

        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO run(issue_id, agent, provider, model, state, verdict, summary, exit_code, started_at, ended_at)
                VALUES (?, 'pi', 'test', 'test-model', 'succeeded', 'done', 'Smoke passed', 0, ?, ?)
                """,
                (issue["id"], now, now),
            )
            connection.execute(
                """
                UPDATE issue
                SET latest_run_id = ?, latest_run_state = 'succeeded', latest_verdict = 'done'
                WHERE id = ?
                """,
                (cursor.lastrowid, issue["id"]),
            )
            connection.commit()

        run = poll_podium_issue_run(
            client,
            int(issue["id"]),
            timeout_seconds=0.1,
            interval_seconds=0.01,
        )

    assert run is not None
    assert run["state"] == "succeeded"
    assert run["verdict"] == "done"


def test_binding_smoke_skill_uses_podium_endpoints_only() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "POST /api/bindings/{name}/issues" in text
    assert "GET /api/issues/{issue_id}/runs" in text
    assert "No Plane API calls" in text
    assert "PLANE_API_URL" not in text
    assert "api/v1/workspaces" not in text
