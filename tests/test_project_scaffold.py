import importlib
from pathlib import Path

import pytest

from config import SymphonyConfig
from tracker_contract import TrackerRole

project_scaffold = importlib.import_module("project_scaffold")
PlaneProjectScaffoldTracker = project_scaffold.PlaneProjectScaffoldTracker
ProjectScaffoldApprovalError = project_scaffold.ProjectScaffoldApprovalError
ProjectScaffoldError = project_scaffold.ProjectScaffoldError
ScaffoldProject = project_scaffold.ScaffoldProject
ScaffoldProjectRequest = project_scaffold.ScaffoldProjectRequest
STANDARD_PROJECT_LABELS = project_scaffold.STANDARD_PROJECT_LABELS
STANDARD_PROJECT_STATES = project_scaffold.STANDARD_PROJECT_STATES
TrackerResource = project_scaffold.TrackerResource
scaffold_project = project_scaffold.scaffold_project


class FakeScaffoldTracker:
    def __init__(self, *, states=None, labels=None):
        self.requests = []
        self.states = tuple(
            states
            if states is not None
            else [TrackerResource(name, f"state-{idx}") for idx, name in enumerate(STANDARD_PROJECT_STATES)]
        )
        self.labels = tuple(
            labels
            if labels is not None
            else [TrackerResource(name, f"label-{idx}") for idx, name in enumerate(STANDARD_PROJECT_LABELS)]
        )

    async def create_project(self, request: ScaffoldProjectRequest) -> ScaffoldProject:
        self.requests.append(request)
        return ScaffoldProject(id="project-new", slug=request.slug, name=request.name)

    async def list_project_states(self, project_id: str) -> tuple[TrackerResource, ...]:
        assert project_id == "project-new"
        return self.states

    async def list_project_labels(self, project_id: str) -> tuple[TrackerResource, ...]:
        assert project_id == "project-new"
        return self.labels


@pytest.mark.asyncio
async def test_project_scaffold_mock_creates_template_binding_and_workflow(tmp_path: Path):
    tracker = FakeScaffoldTracker()
    repo_path = tmp_path / "repo"
    bindings_path = tmp_path / "bindings.yml"

    result = await scaffold_project(
        tracker,
        bindings_path=bindings_path,
        repo_path=repo_path,
        project_name="Tools",
        project_slug="tools",
        base_branch="main",
        default_agent="claude",
    )

    assert result.workflow_path == repo_path / "WORKFLOW.md"
    assert tracker.requests == [
        ScaffoldProjectRequest(
            name="Tools",
            slug="tools",
            states=STANDARD_PROJECT_STATES,
            labels=STANDARD_PROJECT_LABELS,
        )
    ]
    assert "patrol" not in tracker.requests[0].labels
    assert "security" not in tracker.requests[0].labels
    assert result.workflow_path.read_text(encoding="utf-8").startswith("# WORKFLOW.md")

    config = SymphonyConfig.from_env(
        {
            "PLANE_API_URL": "http://plane.example.test",
            "PLANE_API_KEY": "env-secret",
            "PLANE_WORKSPACE_SLUG": "homelab",
            "PI_BIN": "/usr/local/bin/pi",
            "SYMPHONY_BINDINGS_PATH": str(bindings_path),
        }
    )
    binding = config.bindings[0]
    assert binding.name == "tools"
    assert binding.plane_project_id == "project-new"
    assert binding.repo_path == repo_path
    assert binding.base_branch == "main"
    assert binding.default_agent == "claude"
    assert binding.approval_policy.enabled is False
    assert binding.landing_policy.mode == "local"
    assert binding.tracker_contract.project_id == "project-new"
    assert binding.tracker_contract.project_slug == "tools"
    assert binding.tracker_contract.state_roles[TrackerRole.STATE_TODO].uuid == "state-0"
    assert binding.tracker_contract.label_roles[TrackerRole.MODE_PLAN].uuid == "label-0"
    assert binding.tracker_contract.label_roles[TrackerRole.APPROVAL_REQUIRED].uuid == "label-2"
    assert binding.tracker_contract.extra_label_ids == {
        "agent:claude": "label-3",
        "agent:pi": "label-4",
    }


@pytest.mark.asyncio
async def test_project_scaffold_refuses_incomplete_introspection(tmp_path: Path):
    tracker = FakeScaffoldTracker(labels=[TrackerResource("plan", "label-plan")])

    with pytest.raises(ProjectScaffoldError, match="missing required resources"):
        await scaffold_project(
            tracker,
            bindings_path=tmp_path / "bindings.yml",
            repo_path=tmp_path / "repo",
            project_name="Tools",
            project_slug="tools",
            base_branch="main",
        )


@pytest.mark.asyncio
async def test_plane_scaffold_live_creation_requires_explicit_approval():
    class NoMutationTransport:
        async def post(self, path, body):
            raise AssertionError("live Plane mutation must be gated")

    tracker = PlaneProjectScaffoldTracker(
        NoMutationTransport(),
        workspace_slug="homelab",
        approve_live_mutation=False,
    )

    with pytest.raises(ProjectScaffoldApprovalError, match="explicit approval"):
        await tracker.create_project(ScaffoldProjectRequest(name="Tools", slug="tools"))
