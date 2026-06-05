"""Project scaffold helper for adding a new Plane project binding.

The live Plane project creation path is gated: callers must explicitly opt in
before this module sends a create-project request through a Plane transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml

from tracker_contract import TrackerRole


STANDARD_PROJECT_STATES: tuple[str, ...] = (
    "Todo",
    "In Review",
    "Running",
    "Blocked",
    "Done",
)
STANDARD_PROJECT_LABELS: tuple[str, ...] = (
    "plan",
    "build",
    "approval-required",
    "agent:claude",
    "agent:pi",
)

_STATE_ROLE_BY_NAME: dict[str, TrackerRole] = {
    "Todo": TrackerRole.STATE_TODO,
    "In Review": TrackerRole.STATE_IN_REVIEW,
    "Running": TrackerRole.STATE_RUNNING,
    "Blocked": TrackerRole.STATE_BLOCKED,
    "Done": TrackerRole.STATE_DONE,
}
_LABEL_ROLE_BY_NAME: dict[str, TrackerRole] = {
    "plan": TrackerRole.MODE_PLAN,
    "build": TrackerRole.MODE_BUILD,
    "approval-required": TrackerRole.APPROVAL_REQUIRED,
}
_EXTRA_LABEL_NAMES: tuple[str, ...] = ("agent:claude", "agent:pi")

WORKFLOW_STUB = """# WORKFLOW.md

Describe this repository's Symphony workflow before enabling dispatch.

Symphony provides issue id, identifier, title, description, labels, mode, and
schedule context. Keep repo-specific policy here; Symphony only renders it.

## Modes

- execute: Routine implementation or operations work.
- plan: Produce a reviewable plan artifact; do not change production code.
- build: Implement an approved plan.

## Repository rules

- Replace this stub with project-specific instructions before running agents.
"""


class ProjectScaffoldError(RuntimeError):
    """Raised when project scaffolding cannot produce a valid binding."""


class ProjectScaffoldApprovalError(ProjectScaffoldError):
    """Raised when live Plane mutation was not explicitly approved."""


@dataclass(frozen=True)
class ScaffoldProjectRequest:
    name: str
    slug: str
    states: tuple[str, ...] = STANDARD_PROJECT_STATES
    labels: tuple[str, ...] = STANDARD_PROJECT_LABELS


@dataclass(frozen=True)
class ScaffoldProject:
    id: str
    slug: str
    name: str


@dataclass(frozen=True)
class TrackerResource:
    name: str
    uuid: str


@dataclass(frozen=True)
class ProjectScaffoldResult:
    project: ScaffoldProject
    binding_name: str
    bindings_path: Path
    workflow_path: Path


class ProjectScaffoldTracker(Protocol):
    async def create_project(self, request: ScaffoldProjectRequest) -> ScaffoldProject: ...
    async def list_project_states(self, project_id: str) -> tuple[TrackerResource, ...]: ...
    async def list_project_labels(self, project_id: str) -> tuple[TrackerResource, ...]: ...


class PlaneProjectScaffoldTracker:
    """Plane-backed scaffold tracker.

    Real project creation mutates Plane, so it is refused unless
    ``approve_live_mutation`` is true for that exact call path.
    """

    def __init__(self, transport: Any, *, workspace_slug: str, approve_live_mutation: bool = False) -> None:
        self.transport = transport
        self.workspace_slug = workspace_slug
        self.approve_live_mutation = approve_live_mutation

    async def create_project(self, request: ScaffoldProjectRequest) -> ScaffoldProject:
        if not self.approve_live_mutation:
            raise ProjectScaffoldApprovalError(
                "live Plane project creation requires explicit approval"
            )
        body = {
            "name": request.name,
            "identifier": request.slug,
            "states": list(request.states),
            "labels": list(request.labels),
        }
        data = await self.transport.post(f"/workspaces/{self.workspace_slug}/projects/", body)
        return ScaffoldProject(
            id=str(data.get("id") or data.get("project_id") or ""),
            slug=str(data.get("identifier") or data.get("slug") or request.slug),
            name=str(data.get("name") or request.name),
        )

    async def list_project_states(self, project_id: str) -> tuple[TrackerResource, ...]:
        data = await self.transport.get(f"/workspaces/{self.workspace_slug}/projects/{project_id}/states/")
        return _resources_from_response(data)

    async def list_project_labels(self, project_id: str) -> tuple[TrackerResource, ...]:
        data = await self.transport.get(f"/workspaces/{self.workspace_slug}/projects/{project_id}/labels/")
        return _resources_from_response(data)


async def scaffold_project(
    tracker: ProjectScaffoldTracker,
    *,
    bindings_path: Path,
    repo_path: Path,
    project_name: str,
    project_slug: str,
    base_branch: str,
    default_agent: str = "pi",
    approval_enabled: bool = False,
    landing_mode: str = "local",
    workflow_stub: str = WORKFLOW_STUB,
) -> ProjectScaffoldResult:
    """Create a mock/live-gated Plane project and append its binding."""

    request = ScaffoldProjectRequest(name=project_name, slug=project_slug)
    project = await tracker.create_project(request)
    states = await tracker.list_project_states(project.id)
    labels = await tracker.list_project_labels(project.id)
    binding = _binding_entry(
        project=project,
        repo_path=repo_path,
        base_branch=base_branch,
        default_agent=default_agent,
        approval_enabled=approval_enabled,
        landing_mode=landing_mode,
        states=states,
        labels=labels,
    )
    _append_binding(bindings_path, binding)
    workflow_path = repo_path / "WORKFLOW.md"
    _write_workflow_stub(workflow_path, workflow_stub)
    return ProjectScaffoldResult(
        project=project,
        binding_name=project.slug,
        bindings_path=bindings_path,
        workflow_path=workflow_path,
    )


def _binding_entry(
    *,
    project: ScaffoldProject,
    repo_path: Path,
    base_branch: str,
    default_agent: str,
    approval_enabled: bool,
    landing_mode: str,
    states: tuple[TrackerResource, ...],
    labels: tuple[TrackerResource, ...],
) -> dict[str, Any]:
    state_by_name = {item.name: item.uuid for item in states}
    label_by_name = {item.name: item.uuid for item in labels}
    missing_states = [name for name in STANDARD_PROJECT_STATES if name not in state_by_name]
    missing_labels = [name for name in STANDARD_PROJECT_LABELS if name not in label_by_name]
    if missing_states or missing_labels:
        raise ProjectScaffoldError(
            "created project missing required resources: "
            f"states={missing_states} labels={missing_labels}"
        )

    state_roles = {
        role.value: {"name": name, "uuid": state_by_name[name]}
        for name, role in _STATE_ROLE_BY_NAME.items()
    }
    label_roles = {
        role.value: {"name": name, "uuid": label_by_name[name]}
        for name, role in _LABEL_ROLE_BY_NAME.items()
    }
    extra_label_ids = {name: label_by_name[name] for name in _EXTRA_LABEL_NAMES}

    return {
        "name": project.slug,
        "plane_project_id": project.id,
        "repo_path": str(repo_path),
        "base_branch": base_branch,
        "default_agent": default_agent,
        "approval": {"enabled": approval_enabled},
        "landing": {"mode": landing_mode},
        "tracker_contract": {
            "project_slug": project.slug,
            "project_id": project.id,
            "state_roles": state_roles,
            "label_roles": label_roles,
            "extra_label_ids": extra_label_ids,
        },
    }


def _append_binding(path: Path, binding: dict[str, Any]) -> None:
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        raw = None
    if raw is None:
        raw = {"bindings": []}
    if not isinstance(raw, dict) or not isinstance(raw.get("bindings"), list):
        raise ProjectScaffoldError(f"{path}: expected mapping with bindings list")
    raw["bindings"].append(binding)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def _write_workflow_stub(path: Path, content: str) -> None:
    if path.exists():
        raise ProjectScaffoldError(f"{path}: WORKFLOW.md already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _resources_from_response(data: dict[str, Any]) -> tuple[TrackerResource, ...]:
    raw = data.get("results") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        raw = []
    resources: list[TrackerResource] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        uuid = item.get("id") or item.get("uuid")
        if isinstance(name, str) and isinstance(uuid, str):
            resources.append(TrackerResource(name=name, uuid=uuid))
    return tuple(resources)
