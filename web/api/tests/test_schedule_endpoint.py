from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any, cast

from fastapi.testclient import TestClient

main = cast(Any, import_module("web.api.main"))
schedule = cast(Any, import_module("schedule"))


def _create_issue(client: TestClient, binding: str = "homelab") -> dict[str, Any]:
    response = client.post(
        f"/api/bindings/{binding}/issues",
        json={"title": "schedule me", "description": "fixture"},
    )
    assert response.status_code == 201
    return response.json()


def test_post_schedule_next_window_holds_todo_and_wakes(
    client: TestClient, monkeypatch
) -> None:
    issue = _create_issue(client)
    woke = False

    def wake() -> None:
        nonlocal woke
        woke = True

    monkeypatch.setattr(main, "touch_wake_sentinel", wake)

    response = client.post(
        f"/api/issues/{issue['id']}/schedule", json={"not_before": "next_window"}
    )

    assert response.status_code == 200
    row = response.json()
    assert row["state"] == "todo"
    assert row["scheduled_for"] is not None
    assert "Symphony-Schedule:" in row["comments_md"]
    assert 'reason="operator scheduled via Podium"' in row["comments_md"]
    assert woke is True


def test_post_schedule_rejects_noninfra_active_run_and_past(
    client: TestClient,
) -> None:
    coding_issue = _create_issue(client, "symphony")
    assert (
        client.post(
            f"/api/issues/{coding_issue['id']}/schedule",
            json={"not_before": "next_window"},
        ).status_code
        == 400
    )

    active_issue = _create_issue(client)
    with main.connect() as connection:
        connection.execute(
            "UPDATE issue SET latest_run_state = 'queued' WHERE id = ?",
            (active_issue["id"],),
        )
        connection.commit()
    assert (
        client.post(
            f"/api/issues/{active_issue['id']}/schedule",
            json={"not_before": "next_window"},
        ).status_code
        == 409
    )

    past_issue = _create_issue(client)
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert (
        client.post(
            f"/api/issues/{past_issue['id']}/schedule",
            json={"not_before": past, "reason": "too late"},
        ).status_code
        == 422
    )


def test_delete_schedule_clears_hold_and_latest_control_line(
    client: TestClient,
) -> None:
    issue = _create_issue(client)
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    scheduled = client.post(
        f"/api/issues/{issue['id']}/schedule",
        json={"not_before": future, "reason": "operator chose a time"},
    )
    assert scheduled.status_code == 200

    response = client.request(
        "DELETE",
        f"/api/issues/{issue['id']}/schedule",
        json={"reason": "changed my mind"},
    )

    assert response.status_code == 200
    row = response.json()
    assert row["scheduled_for"] is None
    assert "Symphony-Schedule-Cancelled:" in row["comments_md"]
    event = schedule.latest_event(
        [schedule.CandidateComment(body=row["comments_md"], api_order=0)],
        prefer_last=True,
    )
    assert event is not None
    assert event.is_cancellation
    assert event.reason == "changed my mind"


def test_bindings_rows_include_binding_type(client: TestClient) -> None:
    rows = client.get("/api/bindings").json()
    by_name = {row["name"]: row for row in rows}
    assert by_name["homelab"]["binding_type"] == "infra"
    assert by_name["symphony"]["binding_type"] == "coding"


def test_create_issue_with_schedule_is_atomic(client: TestClient) -> None:
    response = client.post(
        "/api/bindings/homelab/issues",
        json={
            "title": "scheduled at create",
            "description": "fixture",
            "schedule": {"not_before": "next_window", "reason": "create held"},
        },
    )

    assert response.status_code == 201
    row = response.json()
    assert row["state"] == "todo"
    assert row["scheduled_for"] is not None
    assert "Symphony-Schedule:" in row["comments_md"]
    assert 'reason="create held"' in row["comments_md"]
