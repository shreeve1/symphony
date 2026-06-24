from __future__ import annotations

from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

main = import_module("web.api.main")


def _set_state(client: TestClient, issue_id: int, state: str) -> None:
    response = client.patch(f"/api/issues/{issue_id}", json={"state": state})
    assert response.status_code == 200


def _set_latest_run_state(issue_id: int, run_state: str | None) -> None:
    # PATCH does not expose latest_run_state, so write it directly. main.connect()
    # honors the per-test PODIUM_DB_PATH set by the client fixture.
    with main.connect() as connection:
        connection.execute(
            "UPDATE issue SET latest_run_state = ? WHERE id = ?",
            (run_state, issue_id),
        )
        connection.commit()


# [5.2]
def test_reply_on_in_review_returns_todo(client: TestClient, issue_id: int) -> None:
    _set_state(client, issue_id, "in_review")

    response = client.post(
        f"/api/issues/{issue_id}/reply", json={"body": "please retry the migration"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "todo"
    assert "### Operator Reply (" in payload["comments_md"]
    assert "please retry the migration" in payload["comments_md"]


def test_reply_response_carries_gate_fields(
    client: TestClient, issue_id: int
) -> None:
    # Regression: the reply response (and its websocket payload) must include
    # the decorated gate fields. The reply flips state to 'todo', where the
    # flyout renders GateHints; a missing unsatisfied_blocked_by/lock_conflicts
    # crashed the frontend ('Application error') on the post-reply re-render.
    _set_state(client, issue_id, "in_review")

    response = client.post(f"/api/issues/{issue_id}/reply", json={"body": "go"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "todo"
    assert "unsatisfied_blocked_by" in payload
    assert "lock_conflicts" in payload
    assert "dependencies_satisfied" in payload


# [5.2b]
def test_reply_writes_wake_sentinel(
    client: TestClient,
    issue_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = tmp_path / "reply-wake"
    monkeypatch.setenv("SYMPHONY_WAKE_SENTINEL_PATH", str(sentinel))
    _set_state(client, issue_id, "in_review")

    response = client.post(f"/api/issues/{issue_id}/reply", json={"body": "go"})

    assert response.status_code == 200
    assert sentinel.is_file()


# [5.2c]
def test_failed_reply_does_not_write_wake_sentinel(
    client: TestClient,
    issue_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = tmp_path / "reply-wake"
    monkeypatch.setenv("SYMPHONY_WAKE_SENTINEL_PATH", str(sentinel))
    with main.connect() as connection:
        connection.execute("UPDATE issue SET state = 'todo' WHERE id = ?", (issue_id,))
        connection.commit()

    response = client.post(f"/api/issues/{issue_id}/reply", json={"body": "nope"})

    assert response.status_code == 409
    assert not sentinel.exists()


# [5.3]
def test_reply_on_blocked_returns_todo(client: TestClient, issue_id: int) -> None:
    _set_state(client, issue_id, "blocked")

    response = client.post(f"/api/issues/{issue_id}/reply", json={"body": "unblocked"})
    assert response.status_code == 200
    assert response.json()["state"] == "todo"


# [5.3]
def test_reply_on_done_reopens_to_todo(client: TestClient, issue_id: int) -> None:
    _set_state(client, issue_id, "done")

    response = client.post(f"/api/issues/{issue_id}/reply", json={"body": "reopen pls"})
    assert response.status_code == 200
    assert response.json()["state"] == "todo"


# [5.4]
def test_reply_on_running_returns_409(client: TestClient, issue_id: int) -> None:
    _set_state(client, issue_id, "running")

    response = client.post(f"/api/issues/{issue_id}/reply", json={"body": "wait"})
    assert response.status_code == 409


# [5.4]
def test_reply_on_todo_returns_409(client: TestClient, issue_id: int) -> None:
    _set_state(client, issue_id, "todo")

    response = client.post(f"/api/issues/{issue_id}/reply", json={"body": "already"})
    assert response.status_code == 409


# [5.4]
def test_reply_on_archived_returns_409(client: TestClient, issue_id: int) -> None:
    _set_state(client, issue_id, "archived")

    response = client.post(f"/api/issues/{issue_id}/reply", json={"body": "restore?"})
    assert response.status_code == 409


# [5.4]
@pytest.mark.parametrize("run_state", ["running", "queued"])
def test_reply_blocked_by_active_run_state(
    client: TestClient, issue_id: int, run_state: str
) -> None:
    _set_state(client, issue_id, "in_review")
    _set_latest_run_state(issue_id, run_state)

    response = client.post(f"/api/issues/{issue_id}/reply", json={"body": "race"})
    assert response.status_code == 409


# [5.5]
@pytest.mark.parametrize("body", ["", "   ", "\n\t  "])
def test_reply_empty_or_whitespace_body_returns_422(
    client: TestClient, issue_id: int, body: str
) -> None:
    _set_state(client, issue_id, "in_review")

    response = client.post(f"/api/issues/{issue_id}/reply", json={"body": body})
    assert response.status_code == 422


# [5.5]
def test_reply_unknown_key_returns_400(client: TestClient, issue_id: int) -> None:
    _set_state(client, issue_id, "in_review")

    response = client.post(
        f"/api/issues/{issue_id}/reply", json={"body": "ok", "flavor": "grape"}
    )
    assert response.status_code == 400


# [5.5]
def test_reply_unknown_issue_returns_404(client: TestClient) -> None:
    response = client.post("/api/issues/999999/reply", json={"body": "ghost"})
    assert response.status_code == 404


# [5.6]
def test_reply_preserves_prior_comments(client: TestClient, issue_id: int) -> None:
    prior = "# Existing thread\n\nAgent said hello."
    response = client.patch(
        f"/api/issues/{issue_id}", json={"comments_md": prior, "state": "in_review"}
    )
    assert response.status_code == 200

    response = client.post(
        f"/api/issues/{issue_id}/reply", json={"body": "operator follow-up"}
    )
    assert response.status_code == 200
    comments = response.json()["comments_md"]
    assert prior in comments
    assert "operator follow-up" in comments
    # Header separates old content from the new reply.
    assert comments.index(prior) < comments.index("### Operator Reply (")
    assert comments.index("### Operator Reply (") < comments.index("operator follow-up")


# [5.6b]
def test_reply_on_null_comments_md(client: TestClient, issue_id: int) -> None:
    _set_state(client, issue_id, "in_review")
    # Direct DB write to simulate a legacy row with NULL comments_md.
    with main.connect() as connection:
        connection.execute(
            "UPDATE issue SET comments_md = NULL WHERE id = ?", (issue_id,)
        )
        connection.commit()

    response = client.post(
        f"/api/issues/{issue_id}/reply", json={"body": "legacy row reply"}
    )
    assert response.status_code == 200
    comments = response.json()["comments_md"]
    assert "### Operator Reply (" in comments
    assert "legacy row reply" in comments


# [5.7]
def test_reply_publishes_issue_updated_event(
    client: TestClient, issue_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_state(client, issue_id, "in_review")
    calls: list[dict[str, Any]] = []

    async def record(message: dict[str, Any]) -> None:
        calls.append(message)

    monkeypatch.setattr(main.websocket_hub, "publish", record)

    response = client.post(f"/api/issues/{issue_id}/reply", json={"body": "go"})
    assert response.status_code == 200

    matches = [m for m in calls if m["type"] == "issue.updated"]
    assert len(matches) == 1
    assert matches[0]["id"] == issue_id
    assert matches[0]["row"]["state"] == "todo"


# [5.8]
def test_reply_updated_at_increases_monotonically(
    client: TestClient, issue_id: int
) -> None:
    stamps = []
    for _ in range(3):
        _set_state(client, issue_id, "in_review")
        response = client.post(f"/api/issues/{issue_id}/reply", json={"body": "ping"})
        assert response.status_code == 200
        stamps.append(datetime.fromisoformat(response.json()["updated_at"]))
    assert stamps[0] < stamps[1] < stamps[2]
