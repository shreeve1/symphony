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
    def __init__(self, *, states=None, labels=None, existing_project=None):
        self.requests = []
        self.created_states = []
        self.created_labels = []
        self.existing_project = existing_project
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

    async def get_project(self, project_id: str) -> ScaffoldProject:
        if self.existing_project is None:
            raise AssertionError("get_project called without existing_project configured")
        return self.existing_project

    async def list_project_states(self, project_id: str) -> tuple[TrackerResource, ...]:
        return self.states

    async def list_project_labels(self, project_id: str) -> tuple[TrackerResource, ...]:
        return self.labels

    async def create_project_state(self, project_id: str, name: str) -> TrackerResource:
        resource = TrackerResource(name, f"state-created-{name.lower().replace(' ', '-')}")
        self.created_states.append(resource)
        self.states = self.states + (resource,)
        return resource

    async def create_project_label(self, project_id: str, name: str) -> TrackerResource:
        resource = TrackerResource(name, f"label-created-{name.replace(':', '-')}")
        self.created_labels.append(resource)
        self.labels = self.labels + (resource,)
        return resource


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
    assert binding.tracker_contract.label_roles[TrackerRole.HAS_WORKTREE].uuid == "label-3"
    assert binding.tracker_contract.extra_label_ids == {
        "agent:claude": "label-4",
        "agent:pi": "label-5",
    }


@pytest.mark.asyncio
async def test_project_scaffold_fills_missing_labels_via_fill_loop(tmp_path: Path):
    # Replaces the old "refuses incomplete introspection" semantics: the
    # post-create fill loop now creates the labels Plane silently dropped.
    tracker = FakeScaffoldTracker(labels=[TrackerResource("plan", "label-plan")])

    await scaffold_project(
        tracker,
        bindings_path=tmp_path / "bindings.yml",
        repo_path=tmp_path / "repo",
        project_name="Tools",
        project_slug="tools",
        base_branch="main",
    )

    created_names = [r.name for r in tracker.created_labels]
    assert set(created_names) == set(STANDARD_PROJECT_LABELS) - {"plan"}
    final_names = [r.name for r in tracker.labels]
    for name in STANDARD_PROJECT_LABELS:
        assert name in final_names


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


# --- Bug 1: fill loop tests ---


@pytest.mark.asyncio
async def test_fill_loop_creates_missing_states_when_plane_returns_defaults(tmp_path: Path):
    # Plane creates 5 defaults; only Todo + Done overlap with STANDARD_PROJECT_STATES.
    # Fill loop must POST the 3 missing states (In Review, Running, Blocked).
    plane_defaults = [
        TrackerResource("Backlog", "state-default-backlog"),
        TrackerResource("Todo", "state-default-todo"),
        TrackerResource("In Progress", "state-default-in-progress"),
        TrackerResource("Done", "state-default-done"),
        TrackerResource("Cancelled", "state-default-cancelled"),
    ]
    tracker = FakeScaffoldTracker(states=plane_defaults, labels=[])

    await scaffold_project(
        tracker,
        bindings_path=tmp_path / "bindings.yml",
        repo_path=tmp_path / "repo",
        project_name="Tools",
        project_slug="tools",
        base_branch="main",
    )

    created_state_names = [r.name for r in tracker.created_states]
    assert set(created_state_names) == {"In Review", "Running", "Blocked"}
    created_label_names = [r.name for r in tracker.created_labels]
    assert set(created_label_names) == set(STANDARD_PROJECT_LABELS)


@pytest.mark.asyncio
async def test_fill_loop_idempotent_when_all_resources_present(tmp_path: Path):
    # FakeScaffoldTracker default state is "all 5 standards pre-populated."
    # Fill loop should observe nothing missing and create nothing.
    tracker = FakeScaffoldTracker()

    await scaffold_project(
        tracker,
        bindings_path=tmp_path / "bindings.yml",
        repo_path=tmp_path / "repo",
        project_name="Tools",
        project_slug="tools",
        base_branch="main",
    )

    assert tracker.created_states == []
    assert tracker.created_labels == []


@pytest.mark.asyncio
async def test_plane_tracker_does_not_send_states_or_labels_in_create_body():
    # Regression guard: Plane silently drops these keys, so the script must
    # not bother sending them. Per-resource POSTs handle states/labels.
    captured = {}

    class CapturingTransport:
        async def post(self, path, body):
            captured["path"] = path
            captured["body"] = body
            return {"id": "p1", "identifier": "tools", "name": "Tools"}

    tracker = PlaneProjectScaffoldTracker(
        CapturingTransport(),
        workspace_slug="homelab",
        approve_live_mutation=True,
    )
    await tracker.create_project(ScaffoldProjectRequest(name="Tools", slug="tools"))

    assert "states" not in captured["body"]
    assert "labels" not in captured["body"]
    assert captured["body"] == {"name": "Tools", "identifier": "tools"}


# --- Bug 2: existing-project-id resume tests ---


@pytest.mark.asyncio
async def test_existing_project_id_skips_create_and_fills(tmp_path: Path):
    existing = ScaffoldProject(id="existing-uuid", slug="tools", name="Tools")
    tracker = FakeScaffoldTracker(
        states=[TrackerResource("Todo", "s-todo"), TrackerResource("Done", "s-done")],
        labels=[],
        existing_project=existing,
    )

    await scaffold_project(
        tracker,
        bindings_path=tmp_path / "bindings.yml",
        repo_path=tmp_path / "repo",
        project_name="Tools",
        project_slug="tools",
        base_branch="main",
        existing_project_id="existing-uuid",
    )

    # create_project was NOT called
    assert tracker.requests == []
    # fill loop ran for missing states + all labels
    assert {r.name for r in tracker.created_states} == {"In Review", "Running", "Blocked"}
    assert {r.name for r in tracker.created_labels} == set(STANDARD_PROJECT_LABELS)


@pytest.mark.asyncio
async def test_existing_project_id_slug_mismatch_aborts(tmp_path: Path):
    existing = ScaffoldProject(id="existing-uuid", slug="OTHER", name="Other")
    tracker = FakeScaffoldTracker(existing_project=existing)

    with pytest.raises(ProjectScaffoldError, match="does not match --slug"):
        await scaffold_project(
            tracker,
            bindings_path=tmp_path / "bindings.yml",
            repo_path=tmp_path / "repo",
            project_name="Tools",
            project_slug="tools",
            base_branch="main",
            existing_project_id="existing-uuid",
        )

    assert tracker.requests == []
    assert tracker.created_states == []
    assert tracker.created_labels == []


def test_cli_existing_project_id_flag():
    from project_scaffold import _build_parser

    parser = _build_parser()
    args = parser.parse_args([
        "--name", "X", "--slug", "x",
        "--repo-path", "/tmp/r", "--base-branch", "main",
        "--bindings-path", "/tmp/b.yml",
        "--existing-project-id", "abc-uuid",
    ])
    assert args.existing_project_id == "abc-uuid"


def test_cli_existing_project_id_mutex_with_dry_run():
    import asyncio

    from project_scaffold import _main

    rc = asyncio.run(
        _main([
            "--name", "X", "--slug", "x",
            "--repo-path", "/tmp/r", "--base-branch", "main",
            "--bindings-path", "/tmp/b.yml",
            "--dry-run", "--existing-project-id", "abc-uuid",
        ])
    )
    assert rc == 1


# --- Bug 3: slug 12-char limit ---


def test_validate_project_slug_accepts_12_char_boundary():
    validate_project_slug("a" * 12)
    validate_project_slug("trading")


def test_validate_project_slug_rejects_13_chars():
    with pytest.raises(ProjectScaffoldError, match="≤12 characters"):
        validate_project_slug("a" * 13)


def test_validate_project_slug_rejects_crypto_trading_agents():
    # The literal slug that crashed the trading rollout on 2026-06-08 ~00:50 UTC.
    with pytest.raises(ProjectScaffoldError, match="≤12 characters"):
        validate_project_slug("crypto-trading-agents")


def test_validate_project_slug_rejects_bad_chars_with_regex_message():
    with pytest.raises(ProjectScaffoldError, match=r"must match \[a-z0-9-\]\+"):
        validate_project_slug("Foo_Bar")
