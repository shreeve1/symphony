from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

main = import_module("web.api.main")
steer_queue = import_module("web.api.steer_queue")


def _insert_running_run(issue_id: int, *, agent: str = "pi") -> int:
    now = datetime.now(UTC).isoformat()
    with main.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO run(issue_id, agent, provider, model, state, started_at)
            VALUES (?, ?, ?, ?, 'running', ?)
            """,
            (issue_id, agent, "test-provider", "test-model", now),
        )
        run_id = int(cursor.lastrowid)
        connection.execute(
            """
            UPDATE issue
               SET state = 'running', latest_run_id = ?, latest_run_state = ?, updated_at = ?
             WHERE id = ?
            """,
            (run_id, "running", now, issue_id),
        )
        connection.commit()
    return run_id


def test_steer_writes_queue_and_comment_without_state_flip(
    client: TestClient,
    issue_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SYMPHONY_RUNTIME_DIR", str(tmp_path))
    run_id = _insert_running_run(issue_id)

    response = client.post(
        f"/api/issues/{issue_id}/steer", json={"body": "switch strategies"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "running"
    assert payload["latest_run_state"] == "running"
    assert "### Operator Steer (" in payload["comments_md"]
    assert "switch strategies" in payload["comments_md"]
    records, _ = steer_queue.read_steer_records(
        str(run_id), 0, environ={"SYMPHONY_RUNTIME_DIR": str(tmp_path)}
    )
    assert len(records) == 1
    assert records[0]["kind"] == "steer"
    assert records[0]["message"] == "switch strategies"
    assert records[0]["issue_id"] == str(issue_id)


def test_abort_writes_abort_record(
    client: TestClient,
    issue_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SYMPHONY_RUNTIME_DIR", str(tmp_path))
    run_id = _insert_running_run(issue_id)

    response = client.post(f"/api/issues/{issue_id}/steer", json={"action": "abort"})

    assert response.status_code == 200
    payload = response.json()
    assert "### Operator Abort (" in payload["comments_md"]
    records, _ = steer_queue.read_steer_records(
        str(run_id), 0, environ={"SYMPHONY_RUNTIME_DIR": str(tmp_path)}
    )
    assert records[0]["kind"] == "abort"


def test_steer_without_active_run_returns_409_and_no_queue(
    client: TestClient,
    issue_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SYMPHONY_RUNTIME_DIR", str(tmp_path))

    response = client.post(f"/api/issues/{issue_id}/steer", json={"body": "go left"})

    assert response.status_code == 409
    assert not (tmp_path / "steer").exists()


def test_steer_accepts_claude_when_binding_persists_sessions(
    client: TestClient,
    issue_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SYMPHONY_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(main, "_binding_claude_persist_for", lambda name: True)
    run_id = _insert_running_run(issue_id, agent="claude")

    response = client.post(f"/api/issues/{issue_id}/steer", json={"body": "go left"})

    assert response.status_code == 200
    payload = response.json()
    assert "### Operator Steer (" in payload["comments_md"]
    assert "go left" in payload["comments_md"]
    records, _ = steer_queue.read_steer_records(
        str(run_id), 0, environ={"SYMPHONY_RUNTIME_DIR": str(tmp_path)}
    )
    assert len(records) == 1
    assert records[0]["kind"] == "steer"
    assert records[0]["message"] == "go left"


def test_steer_rejects_claude_without_persist_message(
    client: TestClient,
    issue_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SYMPHONY_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(main, "_binding_claude_persist_for", lambda name: False)
    _insert_running_run(issue_id, agent="claude")

    response = client.post(f"/api/issues/{issue_id}/steer", json={"body": "go left"})

    assert response.status_code == 409
    assert response.json()["detail"] == "enable claude_persist for live Claude steering"
    assert not (tmp_path / "steer").exists()


def test_steer_unknown_key_returns_400(client: TestClient, issue_id: int) -> None:
    _insert_running_run(issue_id)

    response = client.post(
        f"/api/issues/{issue_id}/steer", json={"body": "ok", "extra": "nope"}
    )

    assert response.status_code == 400


def test_steer_empty_body_returns_422(client: TestClient, issue_id: int) -> None:
    _insert_running_run(issue_id)

    response = client.post(f"/api/issues/{issue_id}/steer", json={"body": "  "})

    assert response.status_code == 422


def test_steer_publishes_issue_updated_event(
    client: TestClient,
    issue_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _insert_running_run(issue_id)
    calls: list[dict[str, Any]] = []

    async def record(message: dict[str, Any]) -> None:
        calls.append(message)

    monkeypatch.setattr(main.websocket_hub, "publish", record)

    response = client.post(f"/api/issues/{issue_id}/steer", json={"body": "nudge"})

    assert response.status_code == 200
    matches = [m for m in calls if m["type"] == "issue.updated"]
    assert len(matches) == 1
    assert matches[0]["id"] == issue_id
    assert matches[0]["row"]["state"] == "running"


def test_read_steer_records_ignores_partial_final_line(tmp_path: Path) -> None:
    path = steer_queue.steer_queue_path(
        "90", environ={"SYMPHONY_RUNTIME_DIR": str(tmp_path)}
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "kind": "steer",
                "run_id": "90",
                "issue_id": "1",
                "message": "first",
            }
        )
        + "\n"
        + '{"kind": "steer"',
        encoding="utf-8",
    )

    records, offset = steer_queue.read_steer_records(
        "90", 0, environ={"SYMPHONY_RUNTIME_DIR": str(tmp_path)}
    )

    assert [r["message"] for r in records] == ["first"]
    assert offset == path.read_bytes().find(b"\n") + 1
