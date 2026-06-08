"""Project scaffold helper for adding a new Plane project binding.

The live Plane project creation path is gated: callers must explicitly opt in
before this module sends a create-project request through a Plane transport.
"""

from __future__ import annotations

import re
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

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_SLUG_MAX_LEN = 12


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

    def __post_init__(self) -> None:
        validate_project_slug(self.slug)


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
    async def get_project(self, project_id: str) -> ScaffoldProject: ...
    async def list_project_states(self, project_id: str) -> tuple[TrackerResource, ...]: ...
    async def list_project_labels(self, project_id: str) -> tuple[TrackerResource, ...]: ...
    async def create_project_state(self, project_id: str, name: str) -> TrackerResource: ...
    async def create_project_label(self, project_id: str, name: str) -> TrackerResource: ...


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
        # Plane silently drops `states`/`labels` on this endpoint; per-resource
        # POSTs after create are the source of truth (see _ensure_project_states).
        body = {
            "name": request.name,
            "identifier": request.slug,
        }
        data = await self.transport.post(f"/workspaces/{self.workspace_slug}/projects/", body)
        return ScaffoldProject(
            id=str(data.get("id") or data.get("project_id") or ""),
            slug=str(data.get("identifier") or data.get("slug") or request.slug),
            name=str(data.get("name") or request.name),
        )

    async def get_project(self, project_id: str) -> ScaffoldProject:
        data = await self.transport.get(f"/workspaces/{self.workspace_slug}/projects/{project_id}/")
        if not isinstance(data, dict):
            raise ProjectScaffoldError(f"unexpected Plane response for project {project_id}")
        return ScaffoldProject(
            id=str(data.get("id") or project_id),
            slug=str(data.get("identifier") or data.get("slug") or ""),
            name=str(data.get("name") or ""),
        )

    async def list_project_states(self, project_id: str) -> tuple[TrackerResource, ...]:
        data = await self.transport.get(f"/workspaces/{self.workspace_slug}/projects/{project_id}/states/")
        return _resources_from_response(data)

    async def list_project_labels(self, project_id: str) -> tuple[TrackerResource, ...]:
        data = await self.transport.get(f"/workspaces/{self.workspace_slug}/projects/{project_id}/labels/")
        return _resources_from_response(data)

    async def create_project_state(self, project_id: str, name: str) -> TrackerResource:
        if not self.approve_live_mutation:
            raise ProjectScaffoldApprovalError(
                "live Plane state creation requires explicit approval"
            )
        data = await self.transport.post(
            f"/workspaces/{self.workspace_slug}/projects/{project_id}/states/",
            {"name": name},
        )
        return TrackerResource(
            name=str(data.get("name") or name),
            uuid=str(data.get("id") or data.get("uuid") or ""),
        )

    async def create_project_label(self, project_id: str, name: str) -> TrackerResource:
        if not self.approve_live_mutation:
            raise ProjectScaffoldApprovalError(
                "live Plane label creation requires explicit approval"
            )
        data = await self.transport.post(
            f"/workspaces/{self.workspace_slug}/projects/{project_id}/labels/",
            {"name": name},
        )
        return TrackerResource(
            name=str(data.get("name") or name),
            uuid=str(data.get("id") or data.get("uuid") or ""),
        )


class MockProjectScaffoldTracker:
    """Mock tracker for dry-run previews. Returns synthetic but valid UUIDs."""

    _COUNTER = 0

    def __init__(self) -> None:
        MockProjectScaffoldTracker._COUNTER += 1
        self._seq = MockProjectScaffoldTracker._COUNTER

    async def create_project(self, request: ScaffoldProjectRequest) -> ScaffoldProject:
        return ScaffoldProject(
            id=f"mock-project-{self._seq}",
            slug=request.slug,
            name=request.name,
        )

    async def get_project(self, project_id: str) -> ScaffoldProject:
        return ScaffoldProject(id=project_id, slug="mock-slug", name="Mock Project")

    async def list_project_states(self, project_id: str) -> tuple[TrackerResource, ...]:
        return tuple(
            TrackerResource(name=name, uuid=f"mock-state-{name.lower().replace(' ', '-')}-{self._seq}")
            for name in STANDARD_PROJECT_STATES
        )

    async def list_project_labels(self, project_id: str) -> tuple[TrackerResource, ...]:
        return tuple(
            TrackerResource(name=name, uuid=f"mock-label-{name.replace(':', '-')}-{self._seq}")
            for name in STANDARD_PROJECT_LABELS
        )

    async def create_project_state(self, project_id: str, name: str) -> TrackerResource:
        return TrackerResource(
            name=name,
            uuid=f"mock-state-{name.lower().replace(' ', '-')}-{self._seq}",
        )

    async def create_project_label(self, project_id: str, name: str) -> TrackerResource:
        return TrackerResource(
            name=name,
            uuid=f"mock-label-{name.replace(':', '-')}-{self._seq}",
        )


async def scaffold_project(
    tracker: ProjectScaffoldTracker,
    *,
    bindings_path: Path,
    bindings_read_path: Path | None = None,
    bindings_output_path: Path | None = None,
    repo_path: Path,
    project_name: str,
    project_slug: str,
    base_branch: str,
    default_agent: str = "pi",
    approval_enabled: bool = False,
    landing_mode: str = "local",
    workflow_stub: str = WORKFLOW_STUB,
    workflow_output_path: Path | None = None,
    workflow_allow_overwrite: bool = False,
    existing_project_id: str | None = None,
) -> ProjectScaffoldResult:
    """Create a mock/live-gated Plane project and append its binding.

    When ``existing_project_id`` is given, the project create step is skipped
    and the existing project is fetched + verified against ``project_slug``.
    The state/label fill loop runs in either case (idempotent).
    """

    request = ScaffoldProjectRequest(name=project_name, slug=project_slug)
    if existing_project_id is None:
        project = await tracker.create_project(request)
    else:
        project = await tracker.get_project(existing_project_id)
        if project.slug != project_slug:
            raise ProjectScaffoldError(
                f"existing project identifier {project.slug!r} does not match "
                f"--slug {project_slug!r}"
            )
    states = await _ensure_project_states(tracker, project.id)
    labels = await _ensure_project_labels(tracker, project.id)
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
    _append_binding(
        bindings_path,
        binding,
        read_path=bindings_read_path,
        output_path=bindings_output_path,
    )
    workflow_path = workflow_output_path or (repo_path / "WORKFLOW.md")
    _write_workflow_stub(workflow_path, workflow_stub, allow_overwrite=workflow_allow_overwrite)
    return ProjectScaffoldResult(
        project=project,
        binding_name=project.slug,
        bindings_path=bindings_output_path or bindings_path,
        workflow_path=workflow_path,
    )


async def _ensure_project_states(
    tracker: ProjectScaffoldTracker, project_id: str
) -> tuple[TrackerResource, ...]:
    existing = await tracker.list_project_states(project_id)
    existing_names = {r.name for r in existing}
    for name in STANDARD_PROJECT_STATES:
        if name not in existing_names:
            await tracker.create_project_state(project_id, name)
    return await tracker.list_project_states(project_id)


async def _ensure_project_labels(
    tracker: ProjectScaffoldTracker, project_id: str
) -> tuple[TrackerResource, ...]:
    existing = await tracker.list_project_labels(project_id)
    existing_names = {r.name for r in existing}
    for name in STANDARD_PROJECT_LABELS:
        if name not in existing_names:
            await tracker.create_project_label(project_id, name)
    return await tracker.list_project_labels(project_id)


def validate_project_slug(slug: str) -> None:
    """Validate a Plane project identifier slug."""
    if len(slug) > _SLUG_MAX_LEN:
        raise ProjectScaffoldError(
            f"invalid slug {slug!r}: must be ≤{_SLUG_MAX_LEN} characters "
            f"(Plane identifier limit); got {len(slug)} chars"
        )
    if not _SLUG_RE.match(slug):
        raise ProjectScaffoldError(
            f"invalid slug {slug!r}: must match [a-z0-9-]+ "
            f"(lowercase alphanumeric with hyphens)"
        )


def _preflight_check(
    *,
    repo_path: Path,
    bindings_path: Path,
    workflow_path: Path,
    project_slug: str,
) -> None:
    """Validate prerequisites before a live Plane mutation."""
    if not repo_path.exists():
        raise ProjectScaffoldError(f"repo_path does not exist: {repo_path}")
    if not repo_path.is_dir():
        raise ProjectScaffoldError(f"repo_path is not a directory: {repo_path}")
    if bindings_path.exists():
        raw = yaml.safe_load(bindings_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("bindings"), list):
            raise ProjectScaffoldError(f"{bindings_path}: expected mapping with bindings list")
        # Reject a name collision before mutating Plane, to avoid orphaning a
        # created project when the post-creation append guard would fire.
        for existing in raw["bindings"]:
            if isinstance(existing, dict) and existing.get("name") == project_slug:
                raise ProjectScaffoldError(f"binding already exists: name={project_slug}")
    if workflow_path.exists():
        raise ProjectScaffoldError(f"{workflow_path}: WORKFLOW.md already exists")


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


def _append_binding(
    path: Path,
    binding: dict[str, Any],
    *,
    read_path: Path | None = None,
    output_path: Path | None = None,
) -> None:
    source = read_path or path
    target = output_path or path

    if source.exists():
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    else:
        raw = None
    if raw is None:
        raw = {"bindings": []}
    if not isinstance(raw, dict) or not isinstance(raw.get("bindings"), list):
        raise ProjectScaffoldError(f"{source}: expected mapping with bindings list")

    # Duplicate guard
    slug = binding.get("name")
    project_id = binding.get("plane_project_id")
    for existing in raw["bindings"]:
        if not isinstance(existing, dict):
            continue
        if existing.get("name") == slug or existing.get("plane_project_id") == project_id:
            raise ProjectScaffoldError(
                f"binding already exists: name={slug} plane_project_id={project_id}"
            )

    raw["bindings"].append(binding)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def _write_workflow_stub(path: Path, content: str, *, allow_overwrite: bool = False) -> None:
    if path.exists() and not allow_overwrite:
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


def _build_parser():
    import argparse

    p = argparse.ArgumentParser(description="Scaffold a new Plane project for Symphony")
    p.add_argument("--name", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("--repo-path", type=Path, required=True)
    p.add_argument("--base-branch", required=True)
    p.add_argument("--bindings-path", type=Path, required=True)
    p.add_argument("--default-agent", default="pi", choices=["pi", "claude"])
    p.add_argument("--approval-enabled", action="store_true")
    p.add_argument("--landing-mode", default="local", choices=["local", "remote"])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--approve-live-mutation", action="store_true")
    p.add_argument(
        "--existing-project-id",
        default=None,
        help="Resume scaffold against an existing Plane project (skip create_project; fill states/labels)",
    )
    return p


def _confirm_live_mutation(slug: str) -> None:
    print(f"Live Plane mutation requested for project '{slug}'.")
    typed = input(f"Type the project slug '{slug}' to confirm: ")
    if typed.strip() != slug:
        raise SystemExit("confirmation failed — live mutation aborted")


async def _main(argv: "list[str] | None" = None) -> int:
    import os

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.dry_run and args.approve_live_mutation:
        print("error: --dry-run and --approve-live-mutation are mutually exclusive")
        return 1
    if args.dry_run and args.existing_project_id:
        print("error: --dry-run and --existing-project-id are mutually exclusive")
        return 1

    validate_project_slug(args.slug)

    bindings_path = Path(os.environ.get("SYMPHONY_BINDINGS_PATH") or args.bindings_path)
    workflow_path = args.repo_path / "WORKFLOW.md"

    if args.dry_run:
        tracker = MockProjectScaffoldTracker()
        preview_bindings = bindings_path.parent / ".bindings.yml.preview"
        preview_workflow = bindings_path.parent / ".WORKFLOW.md.preview"
        result = await scaffold_project(
            tracker,
            bindings_path=bindings_path,
            bindings_read_path=bindings_path if bindings_path.exists() else None,
            bindings_output_path=preview_bindings,
            repo_path=args.repo_path,
            project_name=args.name,
            project_slug=args.slug,
            base_branch=args.base_branch,
            default_agent=args.default_agent,
            approval_enabled=args.approval_enabled,
            landing_mode=args.landing_mode,
            workflow_output_path=preview_workflow,
            workflow_allow_overwrite=True,
        )
        print("Dry-run complete.")
        print(f"  Preview bindings: {result.bindings_path}")
        print(f"  Preview workflow: {result.workflow_path}")
        print("  NOTE: UUIDs in preview are synthetic placeholders.")
        return 0

    if not args.approve_live_mutation:
        print("Live mutation requires --approve-live-mutation")
        return 1

    _preflight_check(
        repo_path=args.repo_path,
        bindings_path=bindings_path,
        workflow_path=workflow_path,
        project_slug=args.slug,
    )

    try:
        api_url = os.environ["PLANE_API_URL"]
        api_key = os.environ["PLANE_API_KEY"]
        workspace_slug = os.environ["PLANE_WORKSPACE_SLUG"]
    except KeyError as exc:
        print(f"error: missing required environment variable {exc}")
        return 1

    _confirm_live_mutation(args.slug)

    from plane_adapter import HttpxPlaneTransport

    transport = HttpxPlaneTransport(api_url, api_key)
    tracker = PlaneProjectScaffoldTracker(
        transport,
        workspace_slug=workspace_slug,
        approve_live_mutation=True,
    )

    try:
        result = await scaffold_project(
            tracker,
            bindings_path=bindings_path,
            repo_path=args.repo_path,
            project_name=args.name,
            project_slug=args.slug,
            base_branch=args.base_branch,
            default_agent=args.default_agent,
            approval_enabled=args.approval_enabled,
            landing_mode=args.landing_mode,
            existing_project_id=args.existing_project_id,
        )
    finally:
        await transport.aclose()

    print("Live scaffold complete.")
    print(f"  Project: {result.project.name} ({result.project.slug})")
    print(f"  Bindings: {result.bindings_path}")
    print(f"  Workflow: {result.workflow_path}")
    return 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(_main()))
