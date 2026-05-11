import logging

import httpx
import pytest

from homelab_router.plane_adapter import InMemoryTransport, PlaneAdapter
from homelab_router.plane_contract import DEFAULT_CONTRACT, PlaneLabel, PlaneState
from plane_poller import (
    HttpxPlaneTransport,
    MAX_MIXED_STATE_PAGES_PER_TICK,
    MAX_PAGES_PER_TICK,
    PAGE_SIZE,
    PlaneContractError,
    PlanePollingAuthError,
    PlanePollingSchemaError,
    build_adapter,
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


@pytest.mark.asyncio
async def test_excludes_todo_with_scheduled_label():
    transport = InMemoryTransport()
    transport.issues = {
        "ordinary": _issue("ordinary", state=PlaneState.TODO.value, labels=["media"]),
        "scheduled": _issue(
            "scheduled", state=PlaneState.TODO.value, labels=["scheduled"]
        ),
    }
    adapter = PlaneAdapter(transport=transport)

    candidates = await fetch_todo_issues(adapter)

    assert [candidate.id for candidate in candidates] == ["ordinary"]


@pytest.mark.asyncio
async def test_excludes_todo_with_scheduled_label_uuid():
    scheduled_uuid = DEFAULT_CONTRACT.label_ids[PlaneLabel.SCHEDULED.value]
    transport = InMemoryTransport()
    transport.issues = {
        "ordinary": _issue("ordinary", state=PlaneState.TODO.value, labels=["media"]),
        "scheduled": _issue(
            "scheduled", state=PlaneState.TODO.value, labels=[scheduled_uuid]
        ),
    }
    adapter = PlaneAdapter(contract=DEFAULT_CONTRACT, transport=transport)

    candidates = await fetch_todo_issues(adapter)

    assert [candidate.id for candidate in candidates] == ["ordinary"]


@pytest.mark.asyncio
async def test_excludes_todo_with_scheduled_label_dict():
    transport = InMemoryTransport()
    transport.issues = {
        "ordinary": _issue("ordinary", state=PlaneState.TODO.value, labels=["media"]),
        "scheduled": _issue(
            "scheduled",
            state=PlaneState.TODO.value,
            labels=[{"name": "scheduled"}],
        ),
    }
    adapter = PlaneAdapter(transport=transport)

    candidates = await fetch_todo_issues(adapter)

    assert [candidate.id for candidate in candidates] == ["ordinary"]


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
    adapter = PlaneAdapter(contract=DEFAULT_CONTRACT, transport=transport)
    todo_state_id = DEFAULT_CONTRACT.state_ids[PlaneState.TODO.value]

    candidates = await fetch_todo_issues(adapter)

    assert [candidate.id for candidate in candidates] == ["first", "second"]
    assert all(f"per_page={PAGE_SIZE}" in path for path in transport.paths)
    assert all(f"state={todo_state_id}" in path for path in transport.paths)
    assert any("cursor=page-2" in path for path in transport.paths)


class StateFilterTransport:
    def __init__(self):
        self.paths = []

    async def get(self, path):
        self.paths.append(path)
        return {"results": [], "next_cursor": None}

    async def post(self, path, body):
        raise AssertionError("poller must not write")

    async def patch(self, path, body):
        raise AssertionError("poller must not write")


@pytest.mark.asyncio
async def test_fetch_todo_issues_passes_server_side_state_filter():
    transport = StateFilterTransport()
    adapter = PlaneAdapter(contract=DEFAULT_CONTRACT, transport=transport)
    todo_state_id = DEFAULT_CONTRACT.state_ids[PlaneState.TODO.value]

    await fetch_todo_issues(adapter)

    assert len(transport.paths) == 1
    assert f"state={todo_state_id}" in transport.paths[0]


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


class MixedStatePaginationTransport:
    def __init__(self):
        self.paths = []

    async def get(self, path):
        self.paths.append(path)
        if len(self.paths) < MAX_PAGES_PER_TICK + 1:
            return {
                "results": [_issue(f"done-{len(self.paths)}", state=PlaneState.DONE.value)],
                "next_cursor": f"page-{len(self.paths) + 1}",
            }
        return {"results": [_issue("late-todo", state=PlaneState.TODO.value)], "next_cursor": None}

    async def post(self, path, body):
        raise AssertionError("poller must not write")

    async def patch(self, path, body):
        raise AssertionError("poller must not write")


@pytest.mark.asyncio
async def test_mixed_state_pages_extend_scan_for_late_todo():
    transport = MixedStatePaginationTransport()
    adapter = PlaneAdapter(contract=DEFAULT_CONTRACT, transport=transport)

    candidates = await fetch_todo_issues(adapter)

    assert [candidate.id for candidate in candidates] == ["late-todo"]
    assert len(transport.paths) == MAX_PAGES_PER_TICK + 1
    assert len(transport.paths) < MAX_MIXED_STATE_PAGES_PER_TICK


class EmptyMixedStatePaginationTransport:
    def __init__(self):
        self.paths = []

    async def get(self, path):
        self.paths.append(path)
        if len(self.paths) == 1:
            return {"results": [_issue("done", state=PlaneState.DONE.value)], "next_cursor": "empty"}
        return {"results": [], "next_cursor": "still-empty"}

    async def post(self, path, body):
        raise AssertionError("poller must not write")

    async def patch(self, path, body):
        raise AssertionError("poller must not write")


@pytest.mark.asyncio
async def test_mixed_state_pages_stop_on_empty_page():
    transport = EmptyMixedStatePaginationTransport()
    adapter = PlaneAdapter(contract=DEFAULT_CONTRACT, transport=transport)

    candidates = await fetch_todo_issues(adapter)

    assert candidates == []
    assert len(transport.paths) == 2


class EndlessMixedStatePaginationTransport:
    def __init__(self):
        self.paths = []

    async def get(self, path):
        self.paths.append(path)
        return {
            "results": [_issue(f"done-{len(self.paths)}", state=PlaneState.DONE.value)],
            "next_cursor": f"page-{len(self.paths) + 1}",
        }

    async def post(self, path, body):
        raise AssertionError("poller must not write")

    async def patch(self, path, body):
        raise AssertionError("poller must not write")


@pytest.mark.asyncio
async def test_mixed_state_pages_stop_at_hard_cap():
    transport = EndlessMixedStatePaginationTransport()
    adapter = PlaneAdapter(contract=DEFAULT_CONTRACT, transport=transport)

    candidates = await fetch_todo_issues(adapter)

    assert candidates == []
    assert len(transport.paths) == MAX_MIXED_STATE_PAGES_PER_TICK


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


@pytest.mark.asyncio
async def test_httpx_transport_writes_with_plane_api_key():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = HttpxPlaneTransport("http://plane.local", "token")
    await transport._client.aclose()
    transport._client = httpx.AsyncClient(
        base_url="http://plane.local/api/v1",
        headers={"X-API-Key": "token", "Content-Type": "application/json"},
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    try:
        patched = await transport.patch("/issues/issue-1", {"state": "Running"})
        posted = await transport.post("/issues/issue-1/comments", {"comment_html": "ok"})
    finally:
        await transport.aclose()

    assert patched == {"ok": True}
    assert posted == {"ok": True}
    assert [request.method for request in requests] == ["PATCH", "POST"]
    assert str(requests[0].url).endswith("/issues/issue-1/")
    assert str(requests[1].url).endswith("/issues/issue-1/comments/")
    assert all(request.headers["X-API-Key"] == "token" for request in requests)


def test_build_adapter_uses_configured_project_uuid():
    adapter = build_adapter(
        InMemoryTransport(),
        workspace_slug="homelab",
        project_id="project-uuid",
    )

    assert adapter._issue_path() == "/workspaces/homelab/projects/project-uuid/issues/"


def test_build_adapter_raises_when_project_id_empty():
    with pytest.raises(PlaneContractError) as exc_info:
        build_adapter(
            InMemoryTransport(),
            workspace_slug="homelab",
            project_id="",
        )

    assert "project_id is required" in str(exc_info.value)


def test_build_adapter_raises_when_workspace_slug_empty():
    with pytest.raises(PlaneContractError) as exc_info:
        build_adapter(
            InMemoryTransport(),
            workspace_slug="",
            project_id="cff68c17-bff6-452f-89b3-9b570613cfaa",
        )

    assert "workspace_slug is required" in str(exc_info.value)


@pytest.mark.asyncio
async def test_httpx_transport_wraps_bare_list_as_results():
    def handler(request):
        return httpx.Response(200, json=[{"id": "issue-1"}, {"id": "issue-2"}])

    transport = HttpxPlaneTransport("http://plane.local", "token")
    await transport._client.aclose()
    transport._client = httpx.AsyncClient(
        base_url="http://plane.local/api/v1",
        headers={"X-API-Key": "token", "Content-Type": "application/json"},
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    try:
        result = await transport.get("/issues/?per_page=50")
    finally:
        await transport.aclose()

    assert result == {"results": [{"id": "issue-1"}, {"id": "issue-2"}], "next_cursor": None}


@pytest.mark.asyncio
async def test_httpx_transport_raises_schema_error_on_non_dict_non_list():
    def handler(request):
        return httpx.Response(200, json="unexpected string")

    transport = HttpxPlaneTransport("http://plane.local", "token")
    await transport._client.aclose()
    transport._client = httpx.AsyncClient(
        base_url="http://plane.local/api/v1",
        headers={"X-API-Key": "token", "Content-Type": "application/json"},
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    try:
        with pytest.raises(PlanePollingSchemaError):
            await transport.get("/issues/issue-1")
    finally:
        await transport.aclose()
