"""Poll Plane for Symphony candidate issues."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

try:
    from homelab_router.plane_adapter import PlaneAdapter, PlaneTransport
    from homelab_router.plane_contract import DEFAULT_CONTRACT, PlaneLabel, PlaneState
except ModuleNotFoundError:
    _repo_env = os.environ.get("HOMELAB_REPO_PATH")
    if not _repo_env:
        raise
    _homelab_repo = Path(_repo_env)
    _src = _homelab_repo / "automation" / "homelab-stack" / "src"
    if str(_src) not in sys.path:
        sys.path.insert(0, str(_src))
    from homelab_router.plane_adapter import PlaneAdapter, PlaneTransport
    from homelab_router.plane_contract import DEFAULT_CONTRACT, PlaneLabel, PlaneState


LOGGER = logging.getLogger(__name__)
PAGE_SIZE = 50
MAX_PAGES_PER_TICK = 3


class PlanePollingAuthError(RuntimeError):
    """Raised when Plane rejects configured credentials."""


class PlanePollingSchemaError(RuntimeError):
    """Raised when Plane returns an unexpected issue shape."""


class PlaneContractError(RuntimeError):
    """Raised when the configured Plane contract fails validation."""


@dataclass(frozen=True)
class CandidateIssue:
    id: str
    identifier: str
    name: str
    description: str
    labels: tuple[str, ...]
    created_at: str


def _extract_labels(
    issue: dict[str, Any],
    label_ids: dict[str, str] | None = None,
) -> tuple[str, ...]:
    labels = issue.get("labels") or []
    uuid_to_name: dict[str, str] = {}
    if label_ids:
        uuid_to_name = {v: k for k, v in label_ids.items()}
    extracted: list[str] = []
    for label in labels:
        if isinstance(label, str):
            extracted.append(uuid_to_name.get(label, label))
        elif isinstance(label, dict):
            name = label.get("name") or label.get("value")
            if isinstance(name, str):
                extracted.append(name)
    return tuple(extracted)


def _is_todo(issue: dict[str, Any], adapter: PlaneAdapter) -> bool:
    state = issue.get("state")
    todo_values = {PlaneState.TODO.value, adapter._resolve_state(PlaneState.TODO)}
    if isinstance(state, str):
        return state in todo_values
    if isinstance(state, dict):
        return state.get("name") == PlaneState.TODO.value or state.get("id") in todo_values
    return False


def _candidate_from_issue(
    issue: dict[str, Any],
    label_ids: dict[str, str] | None = None,
) -> CandidateIssue:
    try:
        return CandidateIssue(
            id=str(issue["id"]),
            identifier=str(issue.get("identifier") or issue.get("sequence_id") or ""),
            name=str(issue["name"]),
            description=str(issue.get("description") or issue.get("description_html") or ""),
            labels=_extract_labels(issue, label_ids=label_ids),
            created_at=str(issue.get("created_at") or ""),
        )
    except KeyError as exc:
        raise PlanePollingSchemaError(f"Plane issue missing field: {exc.args[0]}") from exc


def _page_items(response: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return response
    results = response.get("results")
    if isinstance(results, list):
        return results
    raise PlanePollingSchemaError("Plane response missing results list")


def _next_cursor(response: dict[str, Any] | list[dict[str, Any]]) -> str | None:
    if not isinstance(response, dict):
        return None
    cursor = response.get("next_cursor")
    if cursor:
        return str(cursor)
    next_url = response.get("next")
    if isinstance(next_url, str) and "cursor=" in next_url:
        return next_url.split("cursor=", 1)[1].split("&", 1)[0]
    return None


def _is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    return exc.__class__.__module__.startswith("httpx") and exc.__class__.__name__ in {
        "ConnectError",
        "ConnectTimeout",
        "NetworkError",
        "PoolTimeout",
        "ReadError",
        "ReadTimeout",
        "TimeoutException",
        "TransportError",
        "WriteError",
        "WriteTimeout",
    }


async def fetch_todo_issues(adapter: PlaneAdapter) -> list[CandidateIssue]:
    """Fetch Todo issues that do not require approval."""

    if adapter.transport is None:
        raise RuntimeError("Transport not configured")

    candidates: list[CandidateIssue] = []
    cursor: str | None = None
    pages_fetched = 0
    todo_state_id = adapter._resolve_state(PlaneState.TODO)

    try:
        while pages_fetched < MAX_PAGES_PER_TICK:
            path = f"{adapter._issue_path()}?per_page={PAGE_SIZE}&state={todo_state_id}"
            if cursor:
                path = f"{path}&cursor={cursor}"
            response = await adapter.transport.get(path)
            pages_fetched += 1
            items = _page_items(response)
            label_ids = adapter.contract.label_ids if adapter.contract else None
            for issue in items:
                labels = _extract_labels(issue, label_ids=label_ids)
                if PlaneLabel.APPROVAL_REQUIRED.value in labels:
                    continue
                if not _is_todo(issue, adapter):
                    continue
                candidates.append(_candidate_from_issue(issue, label_ids=label_ids))
            cursor = _next_cursor(response)
            if not cursor:
                return candidates
        LOGGER.info(
            "plane_poll_page_limit_reached pages=%s candidates=%s",
            pages_fetched,
            len(candidates),
        )
        return candidates
    except PlanePollingAuthError:
        LOGGER.error("Plane authentication failed", exc_info=True)
        raise
    except PlanePollingSchemaError:
        LOGGER.error("Plane polling schema error", exc_info=True)
        raise
    except Exception as exc:
        if _is_transient_error(exc):
            LOGGER.warning("Transient Plane polling failure: %s", exc)
            return []
        raise


class HttpxPlaneTransport:
    """Minimal async HTTP transport compatible with PlaneAdapter."""

    def __init__(self, api_url: str, api_key: str) -> None:
        import httpx

        self._client = httpx.AsyncClient(
            base_url=f"{api_url.rstrip('/')}/api/v1",
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            timeout=30,
            follow_redirects=True,
        )

    async def get(self, path: str) -> dict[str, Any]:
        return await self._request("GET", path)

    async def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if method in {"POST", "PATCH"} and "?" not in path and not path.endswith("/"):
            path = f"{path}/"
        response = await self._client.request(method, path, json=body)
        if response.status_code in {401, 403}:
            LOGGER.error("Plane authentication failed with status %s", response.status_code)
            raise PlanePollingAuthError(f"Plane authentication failed: {response.status_code}")
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return {"results": data, "next_cursor": None}
        if not isinstance(data, dict):
            raise PlanePollingSchemaError("Plane response was not an object")
        return data

    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", path, body)

    async def patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", path, body)

    async def aclose(self) -> None:
        await self._client.aclose()


def build_adapter(
    transport: PlaneTransport,
    *,
    workspace_slug: str = DEFAULT_CONTRACT.workspace_slug,
    project_id: str = DEFAULT_CONTRACT.project_id,
) -> PlaneAdapter:
    """Build a PlaneAdapter around the provided transport."""

    contract = replace(
        DEFAULT_CONTRACT,
        workspace_slug=workspace_slug,
        project_id=project_id,
    )
    errors = contract.validate_shape()
    if errors:
        raise PlaneContractError(
            "Plane contract is invalid: " + "; ".join(errors)
        )
    return PlaneAdapter(contract=contract, transport=transport)
