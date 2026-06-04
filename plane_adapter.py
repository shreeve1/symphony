"""Plane client adapter owned by Symphony.

All state/label resolution goes through the per-binding tracker role contract.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol

from tracker_contract import (
    DEFAULT_CONTRACT,
    PlaneContract,
    PlaneLabel,
    PlaneState,
    TrackerContract,
    TrackerRole,
    coerce_label_role,
    coerce_state_role,
)


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
            return {"results": [{"id": uuid, "name": name} for name, uuid in self.labels.items()]}
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
class PlaneAdapter:
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
        return self.resolved_label_ids.get(label.value) or self.contract.label_ids.get(label.value, label.value)

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
        return label == binding.name or label == (self.resolved_label_ids.get(binding.name) or binding.uuid)

    def labels_contain_role(self, labels: tuple[str, ...] | list[str], role: TrackerRole) -> bool:
        return any(self.label_matches_role(label, role) for label in labels)

    async def resolve_label_uuids(self, names: list[str] | None = None) -> dict[str, str]:
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

    async def find_by_external_id(self, external_id: str) -> dict[str, Any] | None:
        if self.transport is None:
            raise RuntimeError("Transport not configured")
        result = await self.transport.get(f"{self._issue_path()}?external_id={external_id}")
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

    async def add_comment(self, issue_id: str, comment: CommentPayload) -> dict[str, Any]:
        if self.transport is None:
            raise RuntimeError("Transport not configured")
        return await self.transport.post(self._comment_path(issue_id), {"comment_html": comment.render()})

    async def transition_state(self, issue_id: str, state: PlaneState | TrackerRole) -> dict[str, Any]:
        if self.transport is None:
            raise RuntimeError("Transport not configured")
        return await self.transport.patch(self._issue_path(issue_id), {"state": self._resolve_state(state)})

    async def add_labels(self, issue_id: str, labels: list[PlaneLabel | TrackerRole]) -> dict[str, Any]:
        if self.transport is None:
            raise RuntimeError("Transport not configured")
        current = await self.transport.get(self._issue_path(issue_id))
        existing_uuids: list[str] = list(current.get("labels") or [])
        new_uuids = [self._resolve_label(label) for label in labels]
        merged = list(dict.fromkeys(existing_uuids + new_uuids))
        return await self.transport.patch(self._issue_path(issue_id), {"labels": merged})

    async def remove_labels(self, issue_id: str, labels: list[PlaneLabel | TrackerRole]) -> dict[str, Any]:
        if self.transport is None:
            raise RuntimeError("Transport not configured")
        current = await self.transport.get(self._issue_path(issue_id))
        remove_uuids = {self._resolve_label(label) for label in labels}
        remaining = [label_uuid for label_uuid in list(current.get("labels") or []) if label_uuid not in remove_uuids]
        return await self.transport.patch(self._issue_path(issue_id), {"labels": remaining})
