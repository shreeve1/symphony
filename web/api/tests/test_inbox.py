from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from importlib import import_module, reload
from typing import Any, cast

from fastapi.testclient import TestClient

main = import_module("web.api.main")
web_api_auth = import_module("web.api.auth")


def test_inbox_returns_in_review_and_blocked_across_bindings(
    client: TestClient,
) -> None:
    # Seed two in_review and one blocked in different bindings.
    ids = _seed_inbox_issues(
        client,
        [
            ("homelab", "HL inbox 1", "in_review"),
            ("trading", "TR inbox 1", "blocked"),
            ("homelab", "HL inbox 2", "in_review"),
        ],
    )

    response = client.get("/api/inbox")
    assert response.status_code == 200
    data = response.json()
    returned_ids = {item["id"] for item in data}
    assert set(ids).issubset(returned_ids)
    # All returned items have correct states.
    for item in data:
        assert item["state"] in ("in_review", "blocked")
    # Items are ordered by COALESCE(last_event_at, updated_at) DESC, id DESC.
    for i in range(len(data) - 1):
        left = data[i]["last_event_at"] or data[i]["updated_at"]
        right = data[i + 1]["last_event_at"] or data[i + 1]["updated_at"]
        assert left >= right


def test_inbox_excludes_archived_binding_issues(client: TestClient) -> None:
    _archive_binding(client, "homelab")
    ids = _seed_inbox_issues(
        client,
        [
            ("homelab", "archived binding", "in_review"),
            ("trading", "live binding", "blocked"),
        ],
    )

    response = client.get("/api/inbox")
    assert response.status_code == 200
    data = response.json()
    returned_ids = {item["id"] for item in data}
    assert ids[0] not in returned_ids
    assert ids[1] in returned_ids


def test_inbox_excludes_dismissed_issues(client: TestClient) -> None:
    now = datetime.now(UTC).isoformat()
    ids = _seed_inbox_issues(client, [("trading", "dismissed", "in_review")])
    dismissed_id = ids[0]

    # Set inbox_dismissed_at >= last_event_at → excluded.
    with main.connect() as connection:
        connection.execute(
            "UPDATE issue SET inbox_dismissed_at = ?, last_event_at = ? WHERE id = ?",
            (now, now, dismissed_id),
        )
        connection.commit()

    response = client.get("/api/inbox")
    assert response.status_code == 200
    data = response.json()
    assert dismissed_id not in {item["id"] for item in data}


def test_inbox_includes_redismissed_issues(client: TestClient) -> None:
    """Issue with dismissal older than last_event_at should reappear."""
    older = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    newer = datetime(2026, 6, 1, tzinfo=UTC).isoformat()
    ids = _seed_inbox_issues(client, [("trading", "redismissed", "in_review")])
    redismissed_id = ids[0]

    with main.connect() as connection:
        connection.execute(
            "UPDATE issue SET inbox_dismissed_at = ?, last_event_at = ? WHERE id = ?",
            (older, newer, redismissed_id),
        )
        connection.commit()

    response = client.get("/api/inbox")
    assert response.status_code == 200
    data = response.json()
    assert redismissed_id in {item["id"] for item in data}


def test_inbox_excludes_todo_and_running_and_done_and_archived(
    client: TestClient,
) -> None:
    ids = _seed_inbox_issues(
        client,
        [
            ("trading", "in_review", "in_review"),
            ("trading", "todo", "todo"),
            ("trading", "running", "running"),
            ("trading", "done", "done"),
            ("trading", "archived", "archived"),
        ],
    )

    response = client.get("/api/inbox")
    assert response.status_code == 200
    data = response.json()
    returned_ids = {item["id"] for item in data}
    assert ids[0] in returned_ids  # in_review
    assert ids[1] not in returned_ids  # todo
    assert ids[2] not in returned_ids  # running
    assert ids[3] not in returned_ids  # done
    assert ids[4] not in returned_ids  # archived


def test_inbox_requires_auth() -> None:
    response = _unauthenticated_client().get("/api/inbox")
    assert response.status_code == 401


def test_inbox_returns_binding_name_and_inbox_dismissed_at(
    client: TestClient,
) -> None:
    ids = _seed_inbox_issues(client, [("trading", "detail check", "in_review")])

    response = client.get("/api/inbox")
    assert response.status_code == 200
    data = response.json()
    item = next(item for item in data if item["id"] == ids[0])
    assert "binding_name" in item
    assert item["binding_name"] == "trading"
    assert "inbox_dismissed_at" in item
    assert item["state"] == "in_review"
    assert "last_event_at" in item


def test_inbox_omits_comments_md_and_context_md(client: TestClient) -> None:
    ids = _seed_inbox_issues(client, [("trading", "no md", "in_review")])

    response = client.get("/api/inbox")
    assert response.status_code == 200
    data = response.json()
    item = next(item for item in data if item["id"] == ids[0])
    assert "comments_md" not in item
    assert "context_md" not in item


def test_dismiss_sets_timestamp_bumps_updated_and_broadcasts(
    client: TestClient,
) -> None:
    ids = _seed_inbox_issues(client, [("trading", "dismiss me", "in_review")])
    issue_id = ids[0]
    before = client.get(f"/api/issues/{issue_id}").json()

    with client.websocket_connect("/api/ws") as ws:
        response = client.post(f"/api/issues/{issue_id}/dismiss")
        message = _receive_json(ws)

    assert response.status_code == 200
    row = response.json()
    assert row["inbox_dismissed_at"] is not None
    assert row["updated_at"] > before["updated_at"]
    assert message["type"] == "issue.updated"
    assert message["id"] == issue_id
    assert message["row"]["inbox_dismissed_at"] == row["inbox_dismissed_at"]


def test_dismiss_rejects_invalid_state_and_unknown_issue(client: TestClient) -> None:
    ids = _seed_inbox_issues(client, [("trading", "todo dismiss", "todo")])

    response = client.post(f"/api/issues/{ids[0]}/dismiss")
    assert response.status_code == 409

    response = client.post("/api/issues/999999/dismiss")
    assert response.status_code == 404


def test_dismiss_removes_issue_from_inbox(client: TestClient) -> None:
    ids = _seed_inbox_issues(client, [("trading", "dismissed hidden", "blocked")])

    response = client.post(f"/api/issues/{ids[0]}/dismiss")
    assert response.status_code == 200

    response = client.get("/api/inbox")
    assert response.status_code == 200
    assert ids[0] not in {item["id"] for item in response.json()}


def test_inbox_resurfaces_when_run_projection_is_newer_than_dismissal(
    client: TestClient,
) -> None:
    ids = _seed_inbox_issues(client, [("trading", "run resurface", "in_review")])
    issue_id = ids[0]
    dismissed = datetime(2026, 6, 1, tzinfo=UTC)
    newer = dismissed + timedelta(minutes=1)
    with main.connect() as connection:
        connection.execute(
            """
            UPDATE issue
            SET inbox_dismissed_at = ?, last_event_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (dismissed.isoformat(), newer.isoformat(), newer.isoformat(), issue_id),
        )
        connection.commit()

    response = client.get("/api/inbox")
    assert response.status_code == 200
    assert issue_id in {item["id"] for item in response.json()}


def test_patch_to_in_review_or_blocked_clears_inbox_dismissal(
    client: TestClient,
) -> None:
    ids = _seed_inbox_issues(
        client,
        [
            ("trading", "patch review", "todo"),
            ("trading", "patch blocked", "done"),
        ],
    )
    with main.connect() as connection:
        connection.executemany(
            "UPDATE issue SET inbox_dismissed_at = ? WHERE id = ?",
            [(datetime.now(UTC).isoformat(), issue_id) for issue_id in ids],
        )
        connection.commit()

    review_response = client.patch(f"/api/issues/{ids[0]}", json={"state": "in_review"})
    blocked_response = client.patch(f"/api/issues/{ids[1]}", json={"state": "blocked"})

    assert review_response.status_code == 200
    assert blocked_response.status_code == 200
    assert review_response.json()["inbox_dismissed_at"] is None
    assert blocked_response.json()["inbox_dismissed_at"] is None


def test_patch_to_other_states_leaves_inbox_dismissal(client: TestClient) -> None:
    ids = _seed_inbox_issues(client, [("trading", "patch todo", "blocked")])
    dismissed = datetime.now(UTC).isoformat()
    with main.connect() as connection:
        connection.execute(
            "UPDATE issue SET inbox_dismissed_at = ? WHERE id = ?", (dismissed, ids[0])
        )
        connection.commit()

    response = client.patch(f"/api/issues/{ids[0]}", json={"state": "todo"})

    assert response.status_code == 200
    assert response.json()["inbox_dismissed_at"] == dismissed


# ── helpers ──────────────────────────────────────────────────────────────


def _seed_inbox_issues(
    client: TestClient,
    specs: list[tuple[str, str, str]],
) -> list[int]:
    ids: list[int] = []
    for binding_name, title, state in specs:
        response = client.post(
            f"/api/bindings/{binding_name}/issues",
            json={"title": title, "description": f"Inbox test for {title}"},
        )
        assert response.status_code == 201
        issue_id = response.json()["id"]
        # Set state directly since POST always creates as 'todo'.
        patch_resp = client.patch(f"/api/issues/{issue_id}", json={"state": state})
        assert patch_resp.status_code == 200
        ids.append(issue_id)
    return ids


def _archive_binding(client: TestClient, name: str) -> None:
    # Archive via direct DB write — no API endpoint for that yet.
    with main.connect() as connection:
        connection.execute("UPDATE binding SET archived = TRUE WHERE name = ?", (name,))
        connection.commit()


def _receive_json(ws, timeout: float = 1.0) -> dict[str, Any]:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(ws.receive_json)
        return cast(dict[str, Any], future.result(timeout=timeout))


def _unauthenticated_client() -> TestClient:
    web_api_auth.reset_rate_limits()
    reload(main)
    app = cast(Any, main.app)
    return TestClient(app)
