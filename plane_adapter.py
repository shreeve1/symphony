"""Tracker adapter seam owned by Symphony.

The scheduler branches on tracker roles and issue lifecycle operations. Plane is
confined to ``PlaneTrackerAdapter`` and its transport implementation.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

from tracker_contract import (
    DEFAULT_CONTRACT,
    PlaneLabel,
    PlaneState,
    TrackerContract,
    TrackerRole,
    coerce_label_role,
    coerce_state_role,
)


LOGGER = logging.getLogger(__name__)
PAGE_SIZE = 50
MAX_PAGES_PER_TICK = 3
MAX_MIXED_STATE_PAGES_PER_TICK = 10


class PlanePollingAuthError(RuntimeError):
    """Raised when Plane rejects configured credentials."""


class PlanePollingSchemaError(RuntimeError):
    """Raised when Plane returns an unexpected issue shape."""


class PlaneRateLimitError(RuntimeError):
    """Raised when Plane asks this binding to cool down before retrying."""

    def __init__(self, message: str, *, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


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
    schedule_not_before: str = ""
    schedule_not_after: str = ""
    schedule_reason: str = ""
    schedule_source: str = ""
    schedule_late: str = ""
    comments_md: str = ""
    context_md: str = ""
    preferred_skill: str | None = None
    worktree_active: bool = False
    base_branch: str = ""
    binding_name: str = ""
    preferred_model: str | None = None
    reasoning_effort: str = "high"
    skill_source: str = ""
    resolved_provider: str = ""
    resolved_model: str = ""


def stable_external_id(runbook: str, external_key: str) -> str:
    digest = hashlib.sha256(external_key.encode()).hexdigest()[:8]
    return f"homelab-{runbook}-{digest}"


@dataclass
class CommentPayload:
    body: str
    outcome: str = ""
    affected_service: str = ""
    dependency_chain: str = ""
    likely_cause: str = ""
    suggested_next_step: str = ""
    diagnostic_excerpt: str = ""

    def render(self) -> str:
        parts: list[str] = [self.body]
        if self.outcome:
            parts.append(f"\n**Outcome:** {self.outcome}")
        if self.affected_service:
            parts.append(f"\n**Affected service:** {self.affected_service}")
        if self.dependency_chain:
            parts.append(f"\n**Dependency chain:** {self.dependency_chain}")
        if self.likely_cause:
            parts.append(f"\n**Likely cause:** {self.likely_cause}")
        if self.suggested_next_step:
            parts.append(f"\n**Suggested next step:** {self.suggested_next_step}")
        if self.diagnostic_excerpt:
            parts.append(f"\n**Diagnostic:**\n```\n{self.diagnostic_excerpt}\n```")
        return "\n".join(parts)


@dataclass
class IssuePayload:
    external_id: str
    name: str
    description: str = ""
    state: PlaneState | TrackerRole = PlaneState.TODO
    labels: list[PlaneLabel | TrackerRole] = field(default_factory=list)
    priority: str | None = None


class PlaneTransport(Protocol):
    async def get(self, path: str) -> dict[str, Any]: ...
    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]: ...
    async def patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]: ...


class ClosablePlaneTransport(PlaneTransport, Protocol):
    async def aclose(self) -> None: ...


class TrackerAdapter(Protocol):
    """Issue-tracker operations the engine is allowed to use."""

    contract: TrackerContract

    def issue_labels(self, issue: dict[str, Any]) -> tuple[str, ...]: ...
    def issue_is_state(self, issue: dict[str, Any], state: TrackerRole) -> bool: ...
    def labels_contain_role(
        self, labels: tuple[str, ...] | list[str], role: TrackerRole
    ) -> bool: ...
    async def list_candidates(self) -> list[CandidateIssue]: ...
    async def list_issues_by_state(
        self,
        state: PlaneState | TrackerRole,
        *,
        per_page: int = PAGE_SIZE,
        max_pages: int = MAX_PAGES_PER_TICK,
    ) -> list[dict[str, Any]]: ...
    async def get_issue(self, issue_id: str) -> dict[str, Any]: ...
    async def list_comments(
        self, issue_id: str, *, max_pages: int = MAX_PAGES_PER_TICK
    ) -> list[dict[str, Any]]: ...
    async def add_comment(
        self, issue_id: str, comment: CommentPayload
    ) -> dict[str, Any]: ...
    async def post_comment(self, issue_id: str, body: str) -> dict[str, Any]: ...
    async def append_context(self, issue_id: str, body: str) -> dict[str, Any]: ...
    async def transition_state(
        self, issue_id: str, state: PlaneState | TrackerRole
    ) -> dict[str, Any]: ...
    async def add_label(
        self, issue_id: str, label: PlaneLabel | TrackerRole
    ) -> dict[str, Any]: ...
    async def remove_label(
        self, issue_id: str, label: PlaneLabel | TrackerRole
    ) -> dict[str, Any]: ...
    async def add_labels(
        self, issue_id: str, labels: list[PlaneLabel | TrackerRole]
    ) -> dict[str, Any]: ...
    async def remove_labels(
        self, issue_id: str, labels: list[PlaneLabel | TrackerRole]
    ) -> dict[str, Any]: ...
    async def get_run(self, run_id: str) -> dict[str, Any] | None: ...
    async def record_run(self, run_row: dict[str, Any]) -> dict[str, Any]: ...


class InMemoryTransport:
    def __init__(self, labels: dict[str, str] | None = None) -> None:
        self.issues: dict[str, dict[str, Any]] = {}
        self.comments: dict[str, list[dict[str, Any]]] = {}
        self.labels: dict[str, str] = dict(labels) if labels else {}
        self._next_id = 1

    async def get(self, path: str) -> dict[str, Any]:
        if "?external_id=" in path:
            ext_id = path.split("external_id=")[1]
            for issue in self.issues.values():
                if issue.get("external_id") == ext_id:
                    return {"results": [issue]}
            return {"results": []}
        if path.endswith("/labels/"):
            return {
                "results": [
                    {"id": uuid, "name": name} for name, uuid in self.labels.items()
                ]
            }
        if "/comments" in path and "/issues/" in path:
            issue_id = path.split("/issues/")[1].split("/comments")[0].strip("/")
            return {"results": list(self.comments.get(issue_id, []))}
        if "/issues/" in path:
            tail = path.split("/issues/")[-1].split("?")[0].strip("/")
            if tail and tail in self.issues:
                return self.issues[tail]
        return {"results": list(self.issues.values())}

    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if "/comments" in path:
            issue_id = path.split("/issues/")[1].split("/comments")[0].strip("/")
            self.comments.setdefault(issue_id, []).append(body)
            return {"id": f"comment-{len(self.comments)}", **body}
        issue_id = f"issue-{self._next_id}"
        self._next_id += 1
        issue = {"id": issue_id, **body}
        self.issues[issue_id] = issue
        return issue

    async def patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        issue_id = path.split("/issues/")[1].split("?")[0].strip("/")
        if issue_id in self.issues:
            self.issues[issue_id].update(body)
            return self.issues[issue_id]
        return {"error": "not found"}


@dataclass
class PlaneTrackerAdapter:
    contract: TrackerContract = DEFAULT_CONTRACT
    transport: PlaneTransport | None = None
    resolved_label_ids: dict[str, str] = field(default_factory=dict)

    def _labels_path(self) -> str:
        project = self.contract.project_id or self.contract.project_slug
        return f"/workspaces/{self.contract.workspace_slug}/projects/{project}/labels/"

    def _issue_path(self, issue_id: str | None = None) -> str:
        project = self.contract.project_id or self.contract.project_slug
        base = f"/workspaces/{self.contract.workspace_slug}/projects/{project}/issues/"
        if issue_id:
            return f"{base}{issue_id}/"
        return base

    def _comment_path(self, issue_id: str) -> str:
        return f"{self._issue_path(issue_id)}comments/"

    def _resolve_state(self, state: PlaneState | TrackerRole) -> str:
        role = coerce_state_role(state)
        return self.contract.state_value_for_role(role)

    def _state_name(self, state: PlaneState | TrackerRole) -> str:
        role = coerce_state_role(state)
        return self.contract.state_name_for_role(role)

    def _resolve_label(self, label: PlaneLabel | TrackerRole) -> str:
        role = coerce_label_role(label)
        if role is not None:
            binding = self.contract.label_binding(role)
            if binding.name in self.resolved_label_ids:
                return self.resolved_label_ids[binding.name]
            return binding.uuid or binding.name
        return self.resolved_label_ids.get(label.value) or self.contract.label_ids.get(
            label.value, label.value
        )

    def _optional_label_value(self, role: TrackerRole) -> str | None:
        binding = self.contract.optional_label_binding(role)
        if binding is None:
            return None
        return self.resolved_label_ids.get(binding.name) or binding.uuid or binding.name

    def _optional_label_name(self, role: TrackerRole) -> str | None:
        return self.contract.optional_label_name_for_role(role)

    def _label_uuid(self, name: str) -> str | None:
        if name in self.resolved_label_ids:
            return self.resolved_label_ids[name]
        return self.contract.label_ids.get(name)

    def label_matches_role(self, label: str, role: TrackerRole) -> bool:
        binding = self.contract.optional_label_binding(role)
        if binding is None:
            return False
        return label == binding.name or label == (
            self.resolved_label_ids.get(binding.name) or binding.uuid
        )

    def issue_labels(self, issue: dict[str, Any]) -> tuple[str, ...]:
        """Return labels normalized through this binding's Tracker Contract."""

        return _extract_labels(issue, label_ids=self.contract.label_ids)

    def issue_is_state(self, issue: dict[str, Any], state: TrackerRole) -> bool:
        """Return whether a raw tracker issue currently satisfies a state role."""

        return _is_state(issue, self, state)

    def labels_contain_role(
        self, labels: tuple[str, ...] | list[str], role: TrackerRole
    ) -> bool:
        return any(self.label_matches_role(label, role) for label in labels)

    async def resolve_label_uuids(
        self, names: list[str] | None = None
    ) -> dict[str, str]:
        if self.transport is None:
            raise RuntimeError("Transport not configured")
        discovered: dict[str, str] = {}
        path: str | None = self._labels_path()
        seen_pages: set[str] = set()
        while path:
            if path in seen_pages:
                break
            seen_pages.add(path)
            result = await self.transport.get(path)
            if not isinstance(result, dict):
                break
            for record in result.get("results", []) or []:
                label_name = record.get("name")
                label_uuid = record.get("id")
                if isinstance(label_name, str) and isinstance(label_uuid, str):
                    discovered[label_name] = label_uuid
            if names is not None and all(name in discovered for name in names):
                break
            next_cursor = result.get("next_cursor") or result.get("next")
            if isinstance(next_cursor, str) and next_cursor:
                if next_cursor.startswith("/"):
                    path = next_cursor
                else:
                    path = f"{self._labels_path()}?cursor={next_cursor}"
            else:
                path = None
        if names is None:
            self.resolved_label_ids.update(discovered)
            return dict(discovered)
        missing = [name for name in names if name not in discovered]
        if missing:
            raise ValueError(f"Plane labels missing from workspace: {sorted(missing)}")
        subset = {name: discovered[name] for name in names}
        self.resolved_label_ids.update(subset)
        return subset

    async def list_issues_by_state(
        self,
        state: PlaneState | TrackerRole,
        *,
        per_page: int = PAGE_SIZE,
        max_pages: int = MAX_PAGES_PER_TICK,
    ) -> list[dict[str, Any]]:
        if self.transport is None:
            raise RuntimeError("Transport not configured")
        state_id = self._resolve_state(state)
        state_role = coerce_state_role(state)
        issues: list[dict[str, Any]] = []
        cursor: str | None = None
        pages = 0
        while pages < max_pages:
            path = f"{self._issue_path()}?per_page={per_page}&state={state_id}"
            if cursor:
                path = f"{path}&cursor={cursor}"
            response = await self.transport.get(path)
            pages += 1
            items = _page_items(response)
            for issue in items:
                if self.issue_is_state(issue, state_role):
                    issues.append(issue)
            cursor = _next_cursor(response)
            if not cursor:
                break
        return issues

    async def list_candidates(self) -> list[CandidateIssue]:
        """Fetch Todo issues that are not held by scheduling."""

        candidates: list[CandidateIssue] = []
        cursor: str | None = None
        pages_fetched = 0
        mixed_state_seen = False
        todo_state_id = self._resolve_state(TrackerRole.STATE_TODO)

        if self.transport is None:
            raise RuntimeError("Transport not configured")

        try:
            while pages_fetched < MAX_MIXED_STATE_PAGES_PER_TICK:
                path = (
                    f"{self._issue_path()}?per_page={PAGE_SIZE}&state={todo_state_id}"
                )
                if cursor:
                    path = f"{path}&cursor={cursor}"
                response = await self.transport.get(path)
                pages_fetched += 1
                items = _page_items(response)
                if not items:
                    return candidates
                for issue in items:
                    labels = self.issue_labels(issue)
                    if self.labels_contain_role(labels, TrackerRole.SCHEDULED):
                        continue
                    if not self.issue_is_state(issue, TrackerRole.STATE_TODO):
                        mixed_state_seen = True
                        continue
                    candidates.append(
                        _candidate_from_issue(issue, label_ids=self.contract.label_ids)
                    )
                cursor = _next_cursor(response)
                if not cursor:
                    return candidates
                if pages_fetched >= MAX_PAGES_PER_TICK and not mixed_state_seen:
                    break
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

    async def get_issue(self, issue_id: str) -> dict[str, Any]:
        if self.transport is None:
            raise RuntimeError("Transport not configured")
        return await self.transport.get(self._issue_path(issue_id))

    async def list_comments(
        self, issue_id: str, *, max_pages: int = MAX_PAGES_PER_TICK
    ) -> list[dict[str, Any]]:
        if self.transport is None:
            raise RuntimeError("Transport not configured")
        comments: list[dict[str, Any]] = []
        base_path = self._comment_path(issue_id)
        path: str | None = base_path
        seen_paths: set[str] = set()
        pages = 0
        while path and pages < max_pages:
            if path in seen_paths:
                break
            seen_paths.add(path)
            response = await self.transport.get(path)
            pages += 1
            raw = response.get("results") if isinstance(response, dict) else response
            if not isinstance(raw, list) or not raw:
                break
            comments.extend(comment for comment in raw if isinstance(comment, dict))
            next_path = response.get("next") if isinstance(response, dict) else None
            next_cursor = (
                response.get("next_cursor") if isinstance(response, dict) else None
            )
            if isinstance(next_path, str) and next_path:
                path = next_path
            elif next_cursor:
                separator = "&" if "?" in base_path else "?"
                path = f"{base_path}{separator}cursor={next_cursor}"
            else:
                break
        return comments

    async def find_by_external_id(self, external_id: str) -> dict[str, Any] | None:
        if self.transport is None:
            raise RuntimeError("Transport not configured")
        result = await self.transport.get(
            f"{self._issue_path()}?external_id={external_id}"
        )
        for issue in result.get("results", []):
            if issue.get("external_id") == external_id:
                return issue
        return None

    async def upsert_issue(self, payload: IssuePayload) -> dict[str, Any]:
        if self.transport is None:
            raise RuntimeError("Transport not configured")
        existing = await self.find_by_external_id(payload.external_id)
        body: dict[str, Any] = {
            "name": payload.name,
            "description_html": payload.description,
            "state": self._resolve_state(payload.state),
        }
        if payload.labels:
            body["labels"] = [self._resolve_label(label) for label in payload.labels]
        if payload.priority is not None:
            body["priority"] = payload.priority
        if existing:
            return await self.transport.patch(self._issue_path(existing["id"]), body)
        body["external_id"] = payload.external_id
        return await self.transport.post(self._issue_path(), body)

    async def add_comment(
        self, issue_id: str, comment: CommentPayload
    ) -> dict[str, Any]:
        if self.transport is None:
            raise RuntimeError("Transport not configured")
        return await self.transport.post(
            self._comment_path(issue_id), {"comment_html": comment.render()}
        )

    async def post_comment(self, issue_id: str, body: str) -> dict[str, Any]:
        return await self.add_comment(issue_id, CommentPayload(body=body))

    async def append_context(self, issue_id: str, body: str) -> dict[str, Any]:
        return await self.add_comment(issue_id, CommentPayload(body=body))

    async def transition_state(
        self, issue_id: str, state: PlaneState | TrackerRole
    ) -> dict[str, Any]:
        if self.transport is None:
            raise RuntimeError("Transport not configured")
        return await self.transport.patch(
            self._issue_path(issue_id), {"state": self._resolve_state(state)}
        )

    async def add_label(
        self, issue_id: str, label: PlaneLabel | TrackerRole
    ) -> dict[str, Any]:
        return await self.add_labels(issue_id, [label])

    async def remove_label(
        self, issue_id: str, label: PlaneLabel | TrackerRole
    ) -> dict[str, Any]:
        return await self.remove_labels(issue_id, [label])

    async def add_labels(
        self, issue_id: str, labels: list[PlaneLabel | TrackerRole]
    ) -> dict[str, Any]:
        if self.transport is None:
            raise RuntimeError("Transport not configured")
        current = await self.transport.get(self._issue_path(issue_id))
        existing_uuids: list[str] = list(current.get("labels") or [])
        new_uuids = [self._resolve_label(label) for label in labels]
        merged = list(dict.fromkeys(existing_uuids + new_uuids))
        return await self.transport.patch(
            self._issue_path(issue_id), {"labels": merged}
        )

    async def remove_labels(
        self, issue_id: str, labels: list[PlaneLabel | TrackerRole]
    ) -> dict[str, Any]:
        if self.transport is None:
            raise RuntimeError("Transport not configured")
        current = await self.transport.get(self._issue_path(issue_id))
        remove_uuids = {self._resolve_label(label) for label in labels}
        remaining = [
            label_uuid
            for label_uuid in list(current.get("labels") or [])
            if label_uuid not in remove_uuids
        ]
        return await self.transport.patch(
            self._issue_path(issue_id), {"labels": remaining}
        )

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        return None

    async def record_run(self, run_row: dict[str, Any]) -> dict[str, Any]:
        return dict(run_row)


PlaneAdapter = PlaneTrackerAdapter


class HttpxPlaneTransport:
    """Minimal async HTTP transport used only by the Plane tracker adapter."""

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

    async def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if method in {"POST", "PATCH"} and "?" not in path and not path.endswith("/"):
            path = f"{path}/"
        response = await self._client.request(method, path, json=body)
        if response.status_code in {401, 403}:
            LOGGER.error(
                "Plane authentication failed with status %s", response.status_code
            )
            raise PlanePollingAuthError(
                f"Plane authentication failed: {response.status_code}"
            )
        if response.status_code == 429:
            retry_after_s = _parse_retry_after(response.headers.get("Retry-After"))
            raise PlaneRateLimitError(
                "Plane rate limited this binding",
                retry_after_s=retry_after_s,
            )
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
    contract: TrackerContract | None = None,
) -> PlaneTrackerAdapter:
    """Build the Plane tracker adapter around the provided transport."""

    resolved_contract = contract or replace(
        DEFAULT_CONTRACT,
        workspace_slug=workspace_slug,
        project_id=project_id,
    )
    errors = resolved_contract.validate_shape()
    if errors:
        raise PlaneContractError("Plane contract is invalid: " + "; ".join(errors))
    return PlaneTrackerAdapter(contract=resolved_contract, transport=transport)


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


def _is_state(
    issue: dict[str, Any], adapter: PlaneTrackerAdapter, state: TrackerRole
) -> bool:
    current = issue.get("state")
    state_name = adapter.contract.state_name_for_role(state)
    wanted = {state_name, adapter._resolve_state(state)}
    if isinstance(current, str):
        return current in wanted
    if isinstance(current, dict):
        return current.get("name") == state_name or current.get("id") in wanted
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
            description=str(
                issue.get("description") or issue.get("description_html") or ""
            ),
            labels=_extract_labels(issue, label_ids=label_ids),
            created_at=str(issue.get("created_at") or ""),
        )
    except KeyError as exc:
        raise PlanePollingSchemaError(
            f"Plane issue missing field: {exc.args[0]}"
        ) from exc


def _page_items(
    response: dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
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


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    text = value.strip()
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0.0, (retry_at.astimezone(UTC) - datetime.now(UTC)).total_seconds())


def _is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, PlaneRateLimitError):
        return False
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
