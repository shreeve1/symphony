import logging

import httpx
import pytest

from homelab_router.plane_adapter import InMemoryTransport, PlaneAdapter
from homelab_router.plane_contract import DEFAULT_CONTRACT, PlaneState
from plane_poller import (
    HttpxPlaneTransport,
    MAX_PAGES_PER_TICK,
    PAGE_SIZE,
    PlanePollingAuthError,
    PlanePollingSchemaError,
    fetch_todo_issues,
)


def _issue(issue_id, state="Todo", labels=None):
    return {
        "id": issue_id,
        "identifier": f"AUTO-{issue_id}",
        "name": f"Issue {issue_id}",
        "description_html": f"Description {issue_id}",
        "state": state,
        "labels": labels or [],
        "created_at": "2026-05-04T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_returns_only_todo_without_approval_required_label():
    transport = InMemoryTransport()
    transport.issues = {
        "todo": _issue("todo", state=PlaneState.TODO.value, labels=["media"]),
        "running": _issue("running", state=PlaneState.RUNNING.value),
        "approval": _issue(
            "approval", state=PlaneState.TODO.value, labels=["approval-required"]
        ),
    }
    adapter = PlaneAdapter(transport=transport)

    candidates = await fetch_todo_issues(adapter)

    assert [candidate.id for candidate in candidates] == ["todo"]


class PaginatedTransport:
    def __init__(self):
        self.paths = []

    async def get(self, path):
        self.paths.append(path)
        if "cursor=page-2" in path:
            return {"results": [_issue("second")], "next_cursor": None}
        return {"results": [_issue("first")], "next_cursor": "page-2"}

    async def post(self, path, body):
        raise AssertionError("poller must not write")

    async def patch(self, path, body):
        raise AssertionError("poller must not write")


@pytest.mark.asyncio
async def test_paginates_at_page_size_50():
    transport = PaginatedTransport()
    adapter = PlaneAdapter(transport=transport)

    candidates = await fetch_todo_issues(adapter)

    assert [candidate.id for candidate in candidates] == ["first", "second"]
    assert all(f"per_page={PAGE_SIZE}" in path for path in transport.paths)
    assert any("cursor=page-2" in path for path in transport.paths)


class EndlessPaginationTransport:
    def __init__(self):
        self.paths = []

    async def get(self, path):
        self.paths.append(path)
        return {"results": [_issue(str(len(self.paths)))], "next_cursor": "next-page"}

    async def post(self, path, body):
        raise AssertionError("poller must not write")

    async def patch(self, path, body):
        raise AssertionError("poller must not write")


@pytest.mark.asyncio
async def test_limits_pages_per_tick_to_avoid_rate_limits(caplog):
    transport = EndlessPaginationTransport()
    adapter = PlaneAdapter(transport=transport)

    with caplog.at_level(logging.INFO):
        candidates = await fetch_todo_issues(adapter)

    assert len(candidates) == MAX_PAGES_PER_TICK
    assert len(transport.paths) == MAX_PAGES_PER_TICK
    assert "plane_poll_page_limit_reached" in caplog.text


class TransientFailureTransport:
    async def get(self, path):
        raise TimeoutError("fake timeout")

    async def post(self, path, body):
        raise AssertionError("poller must not write")

    async def patch(self, path, body):
        raise AssertionError("poller must not write")


class HttpxTransientFailureTransport:
    async def get(self, path):
        raise httpx.ConnectTimeout("fake httpx timeout")

    async def post(self, path, body):
        raise AssertionError("poller must not write")

    async def patch(self, path, body):
        raise AssertionError("poller must not write")


@pytest.mark.asyncio
async def test_transient_network_error_returns_empty_list_with_warning(caplog):
    adapter = PlaneAdapter(transport=TransientFailureTransport())

    with caplog.at_level(logging.WARNING):
        candidates = await fetch_todo_issues(adapter)

    assert candidates == []
    assert "Transient Plane polling failure" in caplog.text


@pytest.mark.asyncio
async def test_httpx_transient_error_returns_empty_list_with_warning(caplog):
    adapter = PlaneAdapter(transport=HttpxTransientFailureTransport())

    with caplog.at_level(logging.WARNING):
        candidates = await fetch_todo_issues(adapter)

    assert candidates == []
    assert "Transient Plane polling failure" in caplog.text


class CurrentCursorTransport:
    async def get(self, path):
        return {"results": [_issue("first")], "cursor": "current-page"}

    async def post(self, path, body):
        raise AssertionError("poller must not write")

    async def patch(self, path, body):
        raise AssertionError("poller must not write")


@pytest.mark.asyncio
async def test_current_cursor_without_next_cursor_does_not_paginate_forever():
    adapter = PlaneAdapter(transport=CurrentCursorTransport())

    candidates = await fetch_todo_issues(adapter)

    assert [candidate.id for candidate in candidates] == ["first"]


class AuthFailureTransport:
    async def get(self, path):
        raise PlanePollingAuthError("fake 401")

    async def post(self, path, body):
        raise AssertionError("poller must not write")

    async def patch(self, path, body):
        raise AssertionError("poller must not write")


@pytest.mark.asyncio
async def test_auth_failure_logs_error_and_raises(caplog):
    adapter = PlaneAdapter(transport=AuthFailureTransport())

    with caplog.at_level(logging.ERROR), pytest.raises(PlanePollingAuthError):
        await fetch_todo_issues(adapter)

    assert "Plane authentication failed" in caplog.text


class SchemaFailureTransport:
    async def get(self, path):
        return {"unexpected": []}

    async def post(self, path, body):
        raise AssertionError("poller must not write")

    async def patch(self, path, body):
        raise AssertionError("poller must not write")


@pytest.mark.asyncio
async def test_schema_error_logs_error_and_raises(caplog):
    adapter = PlaneAdapter(contract=DEFAULT_CONTRACT, transport=SchemaFailureTransport())

    with caplog.at_level(logging.ERROR), pytest.raises(PlanePollingSchemaError):
        await fetch_todo_issues(adapter)

    assert "Plane polling schema error" in caplog.text


@pytest.mark.asyncio
async def test_httpx_transport_follows_plane_trailing_slash_redirect():
    transport = HttpxPlaneTransport("http://plane.local", "token")

    try:
        assert transport._client.follow_redirects is True
    finally:
        await transport.aclose()
