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


# [T.1.1] The no-reopen contract: append succeeds and leaves state UNCHANGED in
# every state — especially `running`, where /reply would 409.
@pytest.mark.parametrize("state", ["todo", "running", "in_review", "blocked", "done"])
def test_comment_appends_without_state_change(
    client: TestClient, issue_id: int, state: str
) -> None:
    _set_state(client, issue_id, state)

    response = client.post(
        f"/api/issues/{issue_id}/comment", json={"body": "patrol note"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == state  # no reopen
    assert "patrol note" in payload["comments_md"]


# [T.1.2] An active run_state (the exact /reply 409 case) still succeeds with no
# flip — a Comment is never gated on the run state.
@pytest.mark.parametrize("run_state", ["queued", "running"])
def test_comment_succeeds_when_run_active(
    client: TestClient, issue_id: int, run_state: str
) -> None:
    _set_state(client, issue_id, "in_review")
    _set_latest_run_state(issue_id, run_state)

    response = client.post(f"/api/issues/{issue_id}/comment", json={"body": "race"})
    assert response.status_code == 200
    assert response.json()["state"] == "in_review"  # no flip despite active run


# [T.1.3]
def test_comment_updated_at_increases_monotonically(
    client: TestClient, issue_id: int
) -> None:
    stamps = []
    for _ in range(3):
        response = client.post(
            f"/api/issues/{issue_id}/comment", json={"body": "ping"}
        )
        assert response.status_code == 200
        stamps.append(datetime.fromisoformat(response.json()["updated_at"]))
    assert stamps[0] < stamps[1] < stamps[2]


# [T.1.3]
def test_comment_publishes_issue_updated_event(
    client: TestClient, issue_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    async def record(message: dict[str, Any]) -> None:
        calls.append(message)

    monkeypatch.setattr(main.websocket_hub, "publish", record)

    response = client.post(f"/api/issues/{issue_id}/comment", json={"body": "go"})
    assert response.status_code == 200

    matches = [m for m in calls if m["type"] == "issue.updated"]
    assert len(matches) == 1
    assert matches[0]["id"] == issue_id


# [T.1.3] The wake sentinel must NOT be touched — a Comment never re-dispatches.
# (Mirror of test_reply_writes_wake_sentinel, asserting the inverse.)
def test_comment_does_not_write_wake_sentinel(
    client: TestClient,
    issue_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = tmp_path / "comment-wake"
    monkeypatch.setenv("SYMPHONY_WAKE_SENTINEL_PATH", str(sentinel))

    response = client.post(
        f"/api/issues/{issue_id}/comment", json={"body": "no wake"}
    )
    assert response.status_code == 200
    assert not sentinel.exists()


# [T.1.4]
@pytest.mark.parametrize("body", ["", "   ", "\n\t  "])
def test_comment_empty_or_whitespace_body_returns_422(
    client: TestClient, issue_id: int, body: str
) -> None:
    response = client.post(f"/api/issues/{issue_id}/comment", json={"body": body})
    assert response.status_code == 422


# [T.1.4]
def test_comment_unknown_key_returns_400(client: TestClient, issue_id: int) -> None:
    response = client.post(
        f"/api/issues/{issue_id}/comment", json={"body": "ok", "flavor": "grape"}
    )
    assert response.status_code == 400


# [T.1.4]
def test_comment_unknown_issue_returns_404(client: TestClient) -> None:
    response = client.post("/api/issues/999999/comment", json={"body": "ghost"})
    assert response.status_code == 404


def test_comment_on_null_comments_md(client: TestClient, issue_id: int) -> None:
    # Direct DB write to simulate a legacy row with NULL comments_md.
    with main.connect() as connection:
        connection.execute(
            "UPDATE issue SET comments_md = NULL WHERE id = ?", (issue_id,)
        )
        connection.commit()

    response = client.post(
        f"/api/issues/{issue_id}/comment", json={"body": "legacy row comment"}
    )
    assert response.status_code == 200
    assert "legacy row comment" in response.json()["comments_md"]


def test_comment_appends_verbatim_without_header(
    client: TestClient, issue_id: int
) -> None:
    prior = "# Existing thread\n\nAgent said hello."
    response = client.patch(f"/api/issues/{issue_id}", json={"comments_md": prior})
    assert response.status_code == 200

    # The patrol worker stamps its own `### Patrol (...)` header; the endpoint
    # injects none. Posting a pre-headed body lands it verbatim after the prior.
    response = client.post(
        f"/api/issues/{issue_id}/comment",
        json={"body": "### Patrol (2026-06-20T00:00:00+00:00)\n\npass"},
    )
    assert response.status_code == 200
    comments = response.json()["comments_md"]
    assert prior in comments
    assert "### Patrol (" in comments
    assert comments.index(prior) < comments.index("### Patrol (")
    # Verbatim: the endpoint never injects an Operator Reply header of its own.
    assert "### Operator Reply (" not in comments
