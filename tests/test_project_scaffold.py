import importlib
from pathlib import Path

import pytest

from config import SymphonyConfig
from tracker_contract import TrackerRole

project_scaffold = importlib.import_module("project_scaffold")
MockProjectScaffoldTracker = project_scaffold.MockProjectScaffoldTracker
PlaneProjectScaffoldTracker = project_scaffold.PlaneProjectScaffoldTracker
ProjectScaffoldApprovalError = project_scaffold.ProjectScaffoldApprovalError
ProjectScaffoldError = project_scaffold.ProjectScaffoldError
ScaffoldProject = project_scaffold.ScaffoldProject
ScaffoldProjectRequest = project_scaffold.ScaffoldProjectRequest
STANDARD_PROJECT_LABELS = project_scaffold.STANDARD_PROJECT_LABELS
STANDARD_PROJECT_STATES = project_scaffold.STANDARD_PROJECT_STATES
TrackerResource = project_scaffold.TrackerResource
validate_project_slug = project_scaffold.validate_project_slug
_preflight_check = project_scaffold._preflight_check
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


# --- MockProjectScaffoldTracker tests ---


@pytest.mark.asyncio
async def test_mock_tracker_returns_synthetic_resources():
    tracker = MockProjectScaffoldTracker()
    project = await tracker.create_project(ScaffoldProjectRequest(name="X", slug="x"))
    assert project.id.startswith("mock-project-")

    states = await tracker.list_project_states(project.id)
    assert len(states) == len(STANDARD_PROJECT_STATES)
    for state in states:
        assert state.uuid.startswith("mock-state-")

    labels = await tracker.list_project_labels(project.id)
    assert len(labels) == len(STANDARD_PROJECT_LABELS)
    for label in labels:
        assert label.uuid.startswith("mock-label-")


@pytest.mark.asyncio
async def test_mock_tracker_generates_unique_ids():
    tracker1 = MockProjectScaffoldTracker()
    tracker2 = MockProjectScaffoldTracker()
    p1 = await tracker1.create_project(ScaffoldProjectRequest(name="A", slug="a"))
    p2 = await tracker2.create_project(ScaffoldProjectRequest(name="B", slug="b"))
    assert p1.id != p2.id


# --- output path tests ---


@pytest.mark.asyncio
async def test_scaffold_project_with_bindings_output_path(tmp_path: Path):
    tracker = FakeScaffoldTracker()
    repo_path = tmp_path / "repo"
    real_bindings = tmp_path / "bindings.yml"
    preview_bindings = tmp_path / ".bindings.yml.preview"

    result = await scaffold_project(
        tracker,
        bindings_path=real_bindings,
        bindings_output_path=preview_bindings,
        repo_path=repo_path,
        project_name="Tools",
        project_slug="tools",
        base_branch="main",
    )

    assert preview_bindings.exists()
    assert not real_bindings.exists()
    assert result.bindings_path == preview_bindings


@pytest.mark.asyncio
async def test_scaffold_project_with_workflow_output_path(tmp_path: Path):
    tracker = FakeScaffoldTracker()
    repo_path = tmp_path / "repo"
    workflow_path = tmp_path / ".WORKFLOW.md.preview"

    result = await scaffold_project(
        tracker,
        bindings_path=tmp_path / "bindings.yml",
        repo_path=repo_path,
        project_name="Tools",
        project_slug="tools",
        base_branch="main",
        workflow_output_path=workflow_path,
    )

    assert workflow_path.exists()
    assert not (repo_path / "WORKFLOW.md").exists()
    assert result.workflow_path == workflow_path


@pytest.mark.asyncio
async def test_scaffold_project_preview_merges_existing_bindings(tmp_path: Path):
    existing_bindings = tmp_path / "bindings.yml"
    existing_bindings.write_text("bindings:\n  - name: existing\n    plane_project_id: p1\n")
    preview_bindings = tmp_path / ".bindings.yml.preview"
    tracker = FakeScaffoldTracker()

    result = await scaffold_project(
        tracker,
        bindings_path=existing_bindings,
        bindings_read_path=existing_bindings,
        bindings_output_path=preview_bindings,
        repo_path=tmp_path / "repo",
        project_name="Tools",
        project_slug="tools",
        base_branch="main",
    )

    text = preview_bindings.read_text(encoding="utf-8")
    assert "existing" in text
    assert "tools" in text


# --- duplicate guard tests ---


@pytest.mark.asyncio
async def test_append_binding_rejects_duplicate_name(tmp_path: Path):
    tracker = FakeScaffoldTracker()
    bindings_path = tmp_path / "bindings.yml"

    await scaffold_project(
        tracker,
        bindings_path=bindings_path,
        repo_path=tmp_path / "repo",
        project_name="Tools",
        project_slug="tools",
        base_branch="main",
    )

    with pytest.raises(ProjectScaffoldError, match="binding already exists"):
        await scaffold_project(
            tracker,
            bindings_path=bindings_path,
            repo_path=tmp_path / "repo2",
            project_name="Tools2",
            project_slug="tools",
            base_branch="main",
        )


@pytest.mark.asyncio
async def test_append_binding_rejects_duplicate_project_id(tmp_path: Path):
    tracker = FakeScaffoldTracker()
    bindings_path = tmp_path / "bindings.yml"

    await scaffold_project(
        tracker,
        bindings_path=bindings_path,
        repo_path=tmp_path / "repo",
        project_name="Tools",
        project_slug="tools",
        base_branch="main",
    )

    with pytest.raises(ProjectScaffoldError, match="binding already exists"):
        await scaffold_project(
            tracker,
            bindings_path=bindings_path,
            repo_path=tmp_path / "repo2",
            project_name="Tools2",
            project_slug="tools2",
            base_branch="main",
        )


# --- slug validation tests ---


def test_validate_project_slug_accepts_valid():
    validate_project_slug("my-project")
    validate_project_slug("a")
    validate_project_slug("abc-123-def")


def test_validate_project_slug_rejects_invalid():
    with pytest.raises(ProjectScaffoldError, match="invalid slug"):
        validate_project_slug("My Project")
    with pytest.raises(ProjectScaffoldError, match="invalid slug"):
        validate_project_slug("my_project")
    with pytest.raises(ProjectScaffoldError, match="invalid slug"):
        validate_project_slug("-project")
    with pytest.raises(ProjectScaffoldError, match="invalid slug"):
        validate_project_slug("project-")
    with pytest.raises(ProjectScaffoldError, match="invalid slug"):
        validate_project_slug("a" * 33)


def test_scaffold_project_request_validates_slug():
    with pytest.raises(ProjectScaffoldError, match="invalid slug"):
        ScaffoldProjectRequest(name="X", slug="Invalid Slug")


# --- preflight check tests ---


def test_preflight_check_rejects_missing_repo(tmp_path: Path):
    missing_repo = tmp_path / "nonexistent"
    with pytest.raises(ProjectScaffoldError, match="repo_path does not exist"):
        _preflight_check(
            repo_path=missing_repo,
            bindings_path=tmp_path / "bindings.yml",
            workflow_path=tmp_path / "WORKFLOW.md",
            project_slug="tools",
        )


def test_preflight_check_rejects_existing_workflow(tmp_path: Path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    workflow_path = tmp_path / "WORKFLOW.md"
    workflow_path.write_text("exists")
    with pytest.raises(ProjectScaffoldError, match="WORKFLOW.md already exists"):
        _preflight_check(
            repo_path=repo_path,
            bindings_path=tmp_path / "bindings.yml",
            workflow_path=workflow_path,
            project_slug="tools",
        )


def test_preflight_check_rejects_malformed_bindings(tmp_path: Path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text("not a mapping")
    with pytest.raises(ProjectScaffoldError, match="expected mapping with bindings list"):
        _preflight_check(
            repo_path=repo_path,
            bindings_path=bindings_path,
            workflow_path=tmp_path / "WORKFLOW.md",
            project_slug="tools",
        )


def test_preflight_check_rejects_duplicate_name(tmp_path: Path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    bindings_path = tmp_path / "bindings.yml"
    bindings_path.write_text("bindings:\n  - name: tools\n    plane_project_id: p1\n")
    with pytest.raises(ProjectScaffoldError, match="binding already exists"):
        _preflight_check(
            repo_path=repo_path,
            bindings_path=bindings_path,
            workflow_path=tmp_path / "WORKFLOW.md",
            project_slug="tools",
        )


# --- CLI tests ---


def test_cli_dry_run_flag():
    from project_scaffold import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["--name", "X", "--slug", "x", "--repo-path", "/tmp/r", "--base-branch", "main", "--bindings-path", "/tmp/b.yml", "--dry-run"])
    assert args.dry_run is True
    assert args.approve_live_mutation is False


def test_cli_approve_live_mutation_flag():
    from project_scaffold import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["--name", "X", "--slug", "x", "--repo-path", "/tmp/r", "--base-branch", "main", "--bindings-path", "/tmp/b.yml", "--approve-live-mutation"])
    assert args.dry_run is False
    assert args.approve_live_mutation is True


def test_cli_rejects_invalid_slug():
    from project_scaffold import _build_parser, validate_project_slug

    parser = _build_parser()
    args = parser.parse_args(["--name", "X", "--slug", "Invalid Slug", "--repo-path", "/tmp/r", "--base-branch", "main", "--bindings-path", "/tmp/b.yml"])
    with pytest.raises(ProjectScaffoldError, match="invalid slug"):
        validate_project_slug(args.slug)


def test_cli_mutually_exclusive_flags():
    import asyncio

    from project_scaffold import _main

    rc = asyncio.run(
        _main([
            "--name", "X", "--slug", "x",
            "--repo-path", "/tmp/r", "--base-branch", "main",
            "--bindings-path", "/tmp/b.yml",
            "--dry-run", "--approve-live-mutation",
        ])
    )
    assert rc == 1
