from __future__ import annotations

import json
import sqlite3
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

podium_issues = cast(Any, import_module("web.cli.podium_issues"))
podium = cast(Any, import_module("web.cli.podium"))
schema = cast(Any, import_module("web.api.schema"))

create_plan_issues = podium_issues.create_plan_issues
resolve_binding_for_cwd = podium_issues.resolve_binding_for_cwd
PodiumIssuesError = podium_issues.PodiumIssuesError


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".kanban" / "issues").mkdir(parents=True)
    (repo / ".kanban" / "issues" / "999-do-not-touch.md").write_text(
        "sentinel", encoding="utf-8"
    )
    return repo


def _make_bindings(
    tmp_path: Path,
    repo: Path,
    *,
    tracker: str = "podium",
    binding_type: str = "coding",
    worktree_default: bool | None = None,
) -> Path:
    path = tmp_path / "bindings.yml"
    binding = {
        "name": "demo",
        "tracker": tracker,
        "type": binding_type,
        "repo_path": str(repo),
        "base_branch": "main",
        "default_agent": "pi",
        "approval": {"enabled": False},
    }
    if worktree_default is not None:
        binding["worktree_default"] = worktree_default
    path.write_text(yaml.safe_dump({"bindings": [binding]}), encoding="utf-8")
    return path


def _make_plan(tmp_path: Path) -> Path:
    path = tmp_path / "plan-slices.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "slices": [
                    {
                        "key": "api",
                        "title": "API slice",
                        "description": "Build the API path.",
                        "acceptance": ["API returns the new field"],
                        "verification": "uv run pytest tests/test_api.py -q",
                        "locks": ["web-api"],
                    },
                    {
                        "key": "ui",
                        "title": "UI slice",
                        "description": "Build the UI path.",
                        "acceptance": ["UI shows the new field"],
                        "verification": "pnpm test ui.spec.ts",
                        "blocked_by": ["api"],
                        "locks": ["web-frontend"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _init_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    with sqlite3.connect(db_path) as connection:
        connection.executescript(schema.SCHEMA_SQL)
        connection.execute("INSERT INTO binding(name, sort_order) VALUES ('demo', 0)")
        connection.commit()
    return db_path


def _issue_rows(db_path: Path) -> list[tuple[Any, ...]]:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            """
            SELECT id, title, description, state, base_branch, preferred_agent,
                   blocked_by, locks, auto_land, preferred_model, worktree_active
            FROM issue ORDER BY id
            """
        ).fetchall()


def test_resolve_binding_matches_repo(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    binding = resolve_binding_for_cwd(repo, bindings)
    assert binding["name"] == "demo"


def test_resolve_binding_no_match_raises(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    bindings = _make_bindings(tmp_path, repo)
    with pytest.raises(PodiumIssuesError, match="no podium binding matches"):
        resolve_binding_for_cwd(other, bindings)


def test_resolve_binding_rejects_non_podium_tracker(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo, tracker="plane")
    with pytest.raises(PodiumIssuesError):
        resolve_binding_for_cwd(repo, bindings)


def test_create_plan_issues_in_dependency_order_with_real_blockers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    plan = _make_plan(tmp_path)
    db_path = _init_db(tmp_path, monkeypatch)
    sentinel = repo / ".kanban" / "issues" / "999-do-not-touch.md"
    before = sentinel.read_text(encoding="utf-8")

    lines = create_plan_issues(repo, plan, bindings_path=bindings)
    assert lines[1:] == ["api 'API slice' -> podium #1", "ui 'UI slice' -> podium #2"]

    rows = _issue_rows(db_path)
    assert [r[1] for r in rows] == ["API slice", "UI slice"]
    assert json.loads(rows[0][6]) == []
    assert json.loads(rows[1][6]) == [1]
    assert json.loads(rows[0][7]) == ["web-api"]
    assert json.loads(rows[1][7]) == ["web-frontend"]
    assert [bool(r[8]) for r in rows] == [True, True]
    assert "uv run pytest tests/test_api.py -q" in rows[0][2]
    assert rows[0][3:6] == ("todo", "main", "pi")
    assert sentinel.read_text(encoding="utf-8") == before


def test_created_slices_use_coding_worktree_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    plan = _make_plan(tmp_path)
    db_path = _init_db(tmp_path, monkeypatch)

    create_plan_issues(repo, plan, bindings_path=bindings)

    rows = _issue_rows(db_path)
    assert [bool(r[10]) for r in rows] == [True, True]


def test_created_slices_honor_disabled_worktree_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(
        tmp_path, repo, binding_type="infra", worktree_default=False
    )
    plan = _make_plan(tmp_path)
    db_path = _init_db(tmp_path, monkeypatch)

    create_plan_issues(repo, plan, bindings_path=bindings)

    rows = _issue_rows(db_path)
    assert [bool(r[10]) for r in rows] == [False, False]


def test_dry_run_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    plan = _make_plan(tmp_path)
    db_path = _init_db(tmp_path, monkeypatch)

    lines = create_plan_issues(repo, plan, bindings_path=bindings, dry_run=True)
    assert any("dry-run" in line for line in lines)
    assert _issue_rows(db_path) == []


def test_unknown_dependency_is_rejected(tmp_path: Path) -> None:
    plan = tmp_path / "bad.yml"
    plan.write_text(
        yaml.safe_dump(
            {
                "slices": [
                    {
                        "key": "ui",
                        "title": "UI",
                        "acceptance": ["works"],
                        "verification": "uv run pytest -q",
                        "blocked_by": ["missing"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(PodiumIssuesError, match="unknown blocked_by"):
        podium_issues._load_plan_slices(plan)


def test_cli_create_from_plan_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    plan = _make_plan(tmp_path)
    _init_db(tmp_path, monkeypatch)
    assert (
        podium.main(
            [
                "issues",
                "create-from-plan",
                str(plan),
                "--cwd",
                str(repo),
                "--bindings",
                str(bindings),
                "--dry-run",
            ]
        )
        == 0
    )


def test_cli_no_binding_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    bindings = _make_bindings(tmp_path, repo)
    plan = _make_plan(tmp_path)
    _init_db(tmp_path, monkeypatch)
    rc = podium.main(
        [
            "issues",
            "create-from-plan",
            str(plan),
            "--cwd",
            str(other),
            "--bindings",
            str(bindings),
        ]
    )
    assert rc == 1
    assert "no podium binding matches" in capsys.readouterr().err


def test_cli_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    plan = _make_plan(tmp_path)
    _init_db(tmp_path, monkeypatch)
    create_plan_issues(repo, plan, bindings_path=bindings)

    assert podium.main(["issues", "list", "--binding", "demo"]) == 0
    out = capsys.readouterr().out
    assert (
        "#1 demo todo auto_land=True blocked_by=[] locks=['web-api'] API slice" in out
    )
    assert (
        "#2 demo todo auto_land=True blocked_by=[1] locks=['web-frontend'] UI slice"
        in out
    )


def _write_plan(tmp_path: Path, slices: list[dict]) -> Path:
    path = tmp_path / "plan.yml"
    path.write_text(yaml.safe_dump({"slices": slices}), encoding="utf-8")
    return path


def _patch_catalog(monkeypatch: pytest.MonkeyPatch, models: list[dict]) -> None:
    monkeypatch.setattr(podium_issues, "load_models", lambda: models)


_CLAUDE_CATALOG = [
    {"id": "claude-opus-4-8", "agent": "claude", "default": True},
    {"id": "claude-fable-5", "agent": "claude"},
]

# A pi model under the binding's default_agent so a model-only slice (no `agent:`)
# resolves against the default agent and succeeds — the T.2.3 "valid model-only" case.
_PI_CATALOG = [
    {"id": "gpt-5.5", "agent": "pi", "provider": "openai-codex", "default": True},
]

# Shared id across agents + two pi providers: bare `claude-opus-4-8` is ambiguous
# for agent=pi (two pi matches), so provider/id is required to disambiguate (T.2.4).
_AMBIGUOUS_CATALOG = [
    {"id": "claude-opus-4-8", "agent": "claude", "default": True},
    {"id": "claude-opus-4-8", "agent": "pi", "provider": "cliproxy"},
    {"id": "claude-opus-4-8", "agent": "pi", "provider": "openai-codex"},
]


def test_model_and_agent_threaded_to_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    plan = _write_plan(
        tmp_path,
        [
            {
                "key": "m",
                "title": "Model slice",
                "description": "pin a model",
                "acceptance": ["model threaded"],
                "verification": "uv run pytest -q",
                "model": "claude-opus-4-8",
                "agent": "claude",
            }
        ],
    )
    db_path = _init_db(tmp_path, monkeypatch)
    _patch_catalog(monkeypatch, _CLAUDE_CATALOG)

    lines = create_plan_issues(repo, plan, bindings_path=bindings)

    rows = _issue_rows(db_path)
    assert len(rows) == 1
    assert rows[0][5] == "claude"  # preferred_agent
    assert rows[0][9] == "claude-opus-4-8"  # preferred_model (new index 9)
    assert lines[1:] == ["m 'Model slice' -> podium #1"]


def test_model_only_uses_default_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    plan = _write_plan(
        tmp_path,
        [
            {
                "key": "mo",
                "title": "Model only",
                "description": "model, no agent",
                "acceptance": ["defaults to pi"],
                "verification": "uv run pytest -q",
                "model": "gpt-5.5",
            }
        ],
    )
    db_path = _init_db(tmp_path, monkeypatch)
    _patch_catalog(monkeypatch, _PI_CATALOG)  # binding default_agent is "pi"

    create_plan_issues(repo, plan, bindings_path=bindings)

    rows = _issue_rows(db_path)
    assert rows[0][5] == "pi"  # preferred_agent = default_agent
    assert rows[0][9] == "gpt-5.5"  # preferred_model


def test_agent_only_overrides_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    plan = _write_plan(
        tmp_path,
        [
            {
                "key": "a",
                "title": "Agent slice",
                "description": "override agent only",
                "acceptance": ["agent threaded"],
                "verification": "uv run pytest -q",
                "agent": "claude",
            }
        ],
    )
    db_path = _init_db(tmp_path, monkeypatch)
    # No model set -> the catalog-validation path never runs, so load_models is
    # left unpatched: the no-model path stays catalog-free and byte-identical.

    create_plan_issues(repo, plan, bindings_path=bindings)

    rows = _issue_rows(db_path)
    assert rows[0][5] == "claude"  # preferred_agent
    assert rows[0][9] is None  # preferred_model


def test_unknown_model_rejected_at_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    plan = _write_plan(
        tmp_path,
        [
            {
                "key": "x",
                "title": "Bad model",
                "description": "unknown model",
                "acceptance": ["rejected"],
                "verification": "uv run pytest -q",
                "model": "nope",
            }
        ],
    )
    db_path = _init_db(tmp_path, monkeypatch)
    _patch_catalog(monkeypatch, _CLAUDE_CATALOG)

    with pytest.raises(PodiumIssuesError, match="model"):
        create_plan_issues(repo, plan, bindings_path=bindings)
    assert _issue_rows(db_path) == []  # no row inserted


def test_agent_model_mismatch_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    plan = _write_plan(
        tmp_path,
        [
            {
                "key": "mm",
                "title": "Mismatch",
                "description": "agent/model mismatch",
                "acceptance": ["rejected"],
                "verification": "uv run pytest -q",
                "model": "claude-fable-5",
                "agent": "pi",
            }
        ],
    )
    db_path = _init_db(tmp_path, monkeypatch)
    _patch_catalog(monkeypatch, _CLAUDE_CATALOG)

    with pytest.raises(PodiumIssuesError, match="requires agent"):
        create_plan_issues(repo, plan, bindings_path=bindings)
    assert _issue_rows(db_path) == []


def test_invalid_agent_rejected(tmp_path: Path) -> None:
    plan = _write_plan(
        tmp_path,
        [
            {
                "key": "ia",
                "title": "Bad agent",
                "acceptance": ["rejected"],
                "verification": "uv run pytest -q",
                "agent": "gemini",
            }
        ],
    )
    with pytest.raises(PodiumIssuesError, match="agent"):
        podium_issues._load_plan_slices(plan)


def test_dry_run_validates_and_shows_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    good = _write_plan(
        tmp_path,
        [
            {
                "key": "g",
                "title": "Good",
                "description": "valid",
                "acceptance": ["ok"],
                "verification": "uv run pytest -q",
                "model": "claude-opus-4-8",
                "agent": "claude",
            }
        ],
    )
    db_path = _init_db(tmp_path, monkeypatch)
    _patch_catalog(monkeypatch, _CLAUDE_CATALOG)

    lines = create_plan_issues(repo, good, bindings_path=bindings, dry_run=True)
    assert any("model=claude-opus-4-8 agent=claude" in line for line in lines)
    assert _issue_rows(db_path) == []  # dry-run inserts nothing

    bad = _write_plan(
        tmp_path,
        [
            {
                "key": "b",
                "title": "Bad",
                "description": "invalid",
                "acceptance": ["ok"],
                "verification": "uv run pytest -q",
                "model": "nope",
            }
        ],
    )
    with pytest.raises(PodiumIssuesError, match="model"):
        create_plan_issues(repo, bad, bindings_path=bindings, dry_run=True)


@pytest.mark.parametrize(
    "field, value", [("model", ""), ("model", "   "), ("agent", ""), ("agent", "\t")]
)
def test_empty_or_whitespace_model_agent_rejected(
    tmp_path: Path, field: str, value: str
) -> None:
    plan = _write_plan(
        tmp_path,
        [
            {
                "key": "e",
                "title": "Empty",
                "acceptance": ["ok"],
                "verification": "uv run pytest -q",
                field: value,
            }
        ],
    )
    with pytest.raises(PodiumIssuesError, match="empty"):
        podium_issues._load_plan_slices(plan)


def test_provider_id_form_disambiguates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    plan = _write_plan(
        tmp_path,
        [
            {
                "key": "d",
                "title": "Disambiguate",
                "description": "provider/id pins a shared id",
                "acceptance": ["resolves"],
                "verification": "uv run pytest -q",
                "model": "cliproxy/claude-opus-4-8",
                "agent": "pi",
            }
        ],
    )
    db_path = _init_db(tmp_path, monkeypatch)
    _patch_catalog(monkeypatch, _AMBIGUOUS_CATALOG)

    # Bare id is ambiguous for agent=pi (two pi providers); provider/id must resolve.
    create_plan_issues(repo, plan, bindings_path=bindings)

    rows = _issue_rows(db_path)
    assert (
        rows[0][9] == "cliproxy/claude-opus-4-8"
    )  # raw form persisted, dispatch re-resolves
    assert rows[0][5] == "pi"  # preferred_agent


def test_malformed_catalog_wrapped_as_podium_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    bindings = _make_bindings(tmp_path, repo)
    plan = _write_plan(
        tmp_path,
        [
            {
                "key": "mc",
                "title": "Bad catalog",
                "description": "models.yml unreadable",
                "acceptance": ["clean error"],
                "verification": "uv run pytest -q",
                "model": "claude-opus-4-8",
            }
        ],
    )
    db_path = _init_db(tmp_path, monkeypatch)

    # A malformed models.yml surfaces as ValueError from load_models; the CLI
    # wraps it so the operator sees a PodiumIssuesError, not a traceback.
    def _boom() -> list[dict]:
        raise ValueError("models must be a list")

    monkeypatch.setattr(podium_issues, "load_models", _boom)

    with pytest.raises(PodiumIssuesError, match="models.yml"):
        create_plan_issues(repo, plan, bindings_path=bindings)
    assert _issue_rows(db_path) == []  # no row inserted on a catalog read failure


# --- sync_from_github (ADR-0042 section 1) ---
# Tests cover the insert-only reconcile contract:
#   * re-running sync never duplicates or mutates an existing row
#   * Verification section -> auto_land=true; no Verification -> auto_land=false
#   * GitHub `## Blocked by` edges map to Podium blocked_by ids
#   * parent-only / non-child issues are filtered out
#   * binding.repo_path without a GitHub remote fails soft (PodiumIssuesError)
# `gh` itself is monkeypatched via `_run_gh_issue_list`; the scheduler's
# `_extract_runnable_verification` is the real implementation under test.


def _init_git_repo(repo: Path, remote_url: str) -> None:
    """Make ``repo`` a git repo whose origin URL is ``remote_url``.

    Mirrors the helper in test_worktree.py; kept local so the podium-issues
    test module has no cross-fixture coupling.
    """
    import subprocess

    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@test"], check=True
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "README.md").write_text("# test", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "initial"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", remote_url],
        check=True,
    )


def _full_issue_rows(db_path: Path) -> list[tuple[Any, ...]]:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            """
            SELECT id, title, description, state, external_id, auto_land,
                   worktree_active, origin, blocked_by, locks
            FROM issue ORDER BY id
            """
        ).fetchall()


def _patch_gh(monkeypatch: pytest.MonkeyPatch, items: list[dict]) -> None:
    monkeypatch.setattr(podium_issues, "_run_gh_issue_list", lambda owner, repo: items)


_CHILD_WITH_VERIFICATION = (
    "## Parent\n\n#1 — Spec parent\n\n"
    "## What to build\n\nDo the thing.\n\n"
    "## Verification\n\n`uv run pytest tests/test_x.py -q`\n"
)
_CHILD_WITHOUT_VERIFICATION = (
    "## Parent\n\n#1 — Spec parent\n\n## What to build\n\nDo the thing.\n"
)
_PARENT_ONLY = (
    "## Problem Statement\n\nThis is the spec, not a child.\n\n"
    "## Acceptance criteria\n\n- [ ] Parent closes last.\n"
)


def test_sync_inserts_child_with_verification_sets_auto_land_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    _init_git_repo(repo, "git@github-personal:owner/repo.git")
    bindings = _make_bindings(tmp_path, repo)
    db_path = _init_db(tmp_path, monkeypatch)
    _patch_gh(
        monkeypatch,
        [
            {
                "number": 10,
                "title": "Child with verify",
                "body": _CHILD_WITH_VERIFICATION,
            }
        ],
    )

    lines = podium_issues.sync_from_github(repo, bindings_path=bindings)

    rows = _full_issue_rows(db_path)
    assert len(rows) == 1
    assert rows[0][1] == "Child with verify"
    assert rows[0][2] == _CHILD_WITH_VERIFICATION
    assert rows[0][3] == "todo"
    assert rows[0][4] == "github:owner/repo#10"
    assert bool(rows[0][5]) is True  # auto_land: Verification present
    assert bool(rows[0][6]) is True  # worktree_active (coding binding default)
    assert rows[0][7] == "operator"
    assert json.loads(rows[0][8]) == []
    assert json.loads(rows[0][9]) == []
    assert any("-> podium #1" in line for line in lines)
    assert any("inserted=1 skipped=0" in line for line in lines)


def test_sync_inserts_child_without_verification_sets_auto_land_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    _init_git_repo(repo, "git@github-personal:owner/repo.git")
    bindings = _make_bindings(tmp_path, repo)
    db_path = _init_db(tmp_path, monkeypatch)
    _patch_gh(
        monkeypatch,
        [
            {
                "number": 11,
                "title": "Child no-verify",
                "body": _CHILD_WITHOUT_VERIFICATION,
            }
        ],
    )

    podium_issues.sync_from_github(repo, bindings_path=bindings)

    rows = _full_issue_rows(db_path)
    assert len(rows) == 1
    assert bool(rows[0][5]) is False  # auto_land: no Verification section
    assert rows[0][4] == "github:owner/repo#11"


def test_sync_skips_issues_without_parent_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    _init_git_repo(repo, "git@github-personal:owner/repo.git")
    bindings = _make_bindings(tmp_path, repo)
    db_path = _init_db(tmp_path, monkeypatch)
    _patch_gh(
        monkeypatch,
        [
            {"number": 1, "title": "Spec parent", "body": _PARENT_ONLY},
            {
                "number": 2,
                "title": "Child",
                "body": _CHILD_WITH_VERIFICATION,
            },
        ],
    )

    lines = podium_issues.sync_from_github(repo, bindings_path=bindings)

    rows = _full_issue_rows(db_path)
    assert len(rows) == 1
    assert rows[0][4] == "github:owner/repo#2"
    assert any("child_issues=1" in line for line in lines)


def test_sync_rerun_is_idempotent_and_does_not_mutate_existing_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    _init_git_repo(repo, "git@github-personal:owner/repo.git")
    bindings = _make_bindings(tmp_path, repo)
    db_path = _init_db(tmp_path, monkeypatch)
    _patch_gh(
        monkeypatch,
        [
            {
                "number": 20,
                "title": "First title",
                "body": _CHILD_WITH_VERIFICATION,
            }
        ],
    )

    podium_issues.sync_from_github(repo, bindings_path=bindings)
    first_rows = _full_issue_rows(db_path)
    assert len(first_rows) == 1

    # Operator mutates the GitHub-side title/body between syncs. The re-run
    # must NOT overwrite the Podium row (insert-only contract).
    _patch_gh(
        monkeypatch,
        [
            {
                "number": 20,
                "title": "Mutated GitHub title",
                "body": _CHILD_WITH_VERIFICATION + "\n## Extra\n\nmutated.\n",
            }
        ],
    )
    lines = podium_issues.sync_from_github(repo, bindings_path=bindings)
    second_rows = _full_issue_rows(db_path)

    assert len(second_rows) == 1
    assert second_rows[0][0] == first_rows[0][0]  # same id
    assert second_rows[0][1] == first_rows[0][1]  # title untouched
    assert second_rows[0][2] == first_rows[0][2]  # body untouched
    assert any("-> existing podium #1 (skip)" in line for line in lines)
    assert any("inserted=0 skipped=1" in line for line in lines)


def test_sync_maps_blocked_by_to_podium_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    _init_git_repo(repo, "git@github-personal:owner/repo.git")
    bindings = _make_bindings(tmp_path, repo)
    db_path = _init_db(tmp_path, monkeypatch)
    # Issue #5 is a blocker already mirrored earlier; #6 depends on it.
    _patch_gh(
        monkeypatch,
        [
            {
                "number": 5,
                "title": "Blocker",
                "body": _CHILD_WITH_VERIFICATION,
            }
        ],
    )
    podium_issues.sync_from_github(repo, bindings_path=bindings)
    with sqlite3.connect(db_path) as connection:
        blocker_id = connection.execute(
            "SELECT id FROM issue WHERE external_id = ?",
            ("github:owner/repo#5",),
        ).fetchone()[0]

    dependent_body = (
        "## Parent\n\n#1 — Spec parent\n\n"
        "## Blocked by\n\n- #5 — Blocker\n\n"
        "## What to build\n\nDepends on the blocker.\n\n"
        "## Verification\n\n`uv run pytest -q`\n"
    )
    _patch_gh(
        monkeypatch,
        [{"number": 6, "title": "Dependent", "body": dependent_body}],
    )
    podium_issues.sync_from_github(repo, bindings_path=bindings)

    rows = _full_issue_rows(db_path)
    by_external = {row[4]: row for row in rows}
    assert by_external["github:owner/repo#6"][0] > blocker_id
    assert json.loads(by_external["github:owner/repo#6"][8]) == [blocker_id]


def test_sync_drops_blocked_by_edges_not_in_podium(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    _init_git_repo(repo, "git@github-personal:owner/repo.git")
    bindings = _make_bindings(tmp_path, repo)
    db_path = _init_db(tmp_path, monkeypatch)
    body = (
        "## Parent\n\n#1 — Spec parent\n\n"
        "## Blocked by\n\n- #999 — Not in Podium yet\n\n"
        "## What to build\n\nWill resolve later.\n\n"
        "## Verification\n\n`uv run pytest -q`\n"
    )
    _patch_gh(
        monkeypatch,
        [{"number": 7, "title": "Later-unblocked", "body": body}],
    )

    podium_issues.sync_from_github(repo, bindings_path=bindings)

    rows = _full_issue_rows(db_path)
    assert len(rows) == 1
    assert json.loads(rows[0][8]) == []


def test_sync_maps_blocked_by_within_single_pass_newest_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`gh issue list` returns newest-first; a dependent listed before its
    blocker must still resolve the edge in one sync pass (blockers carry lower
    numbers because to-tickets publishes them first). Regression for the edge
    being silently dropped when the dependent was inserted before the blocker.
    """
    repo = _make_repo(tmp_path)
    _init_git_repo(repo, "git@github-personal:owner/repo.git")
    bindings = _make_bindings(tmp_path, repo)
    db_path = _init_db(tmp_path, monkeypatch)
    dependent_body = (
        "## Parent\n\n#1 — Spec parent\n\n"
        "## Blocked by\n\n- #6 — Blocker\n\n"
        "## What to build\n\nDepends on the blocker.\n\n"
        "## Verification\n\n`uv run pytest -q`\n"
    )
    # Dependent (#7) listed BEFORE its blocker (#6), as gh returns newest-first.
    _patch_gh(
        monkeypatch,
        [
            {"number": 7, "title": "Dependent", "body": dependent_body},
            {"number": 6, "title": "Blocker", "body": _CHILD_WITH_VERIFICATION},
        ],
    )

    podium_issues.sync_from_github(repo, bindings_path=bindings)

    rows = _full_issue_rows(db_path)
    by_external = {row[4]: row for row in rows}
    blocker_id = by_external["github:owner/repo#6"][0]
    assert json.loads(by_external["github:owner/repo#7"][8]) == [blocker_id]


def test_sync_no_github_remote_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo, "https://gitlab.example.com/owner/repo.git")  # non-GitHub
    bindings = _make_bindings(tmp_path, repo)
    _init_db(tmp_path, monkeypatch)

    with pytest.raises(PodiumIssuesError, match="does not resolve to a GitHub"):
        podium_issues.sync_from_github(repo, bindings_path=bindings)


def test_sync_dry_run_inserts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    _init_git_repo(repo, "git@github-personal:owner/repo.git")
    bindings = _make_bindings(tmp_path, repo)
    db_path = _init_db(tmp_path, monkeypatch)
    _patch_gh(
        monkeypatch,
        [
            {
                "number": 30,
                "title": "Dry-run",
                "body": _CHILD_WITH_VERIFICATION,
            }
        ],
    )

    lines = podium_issues.sync_from_github(repo, bindings_path=bindings, dry_run=True)

    assert _full_issue_rows(db_path) == []
    assert any("dry-run" in line for line in lines)
    assert any("auto_land=True" in line for line in lines)


def test_cli_sync_from_github_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path)
    _init_git_repo(repo, "git@github-personal:owner/repo.git")
    bindings = _make_bindings(tmp_path, repo)
    _init_db(tmp_path, monkeypatch)
    _patch_gh(
        monkeypatch,
        [
            {
                "number": 40,
                "title": "Cli dry-run",
                "body": _CHILD_WITH_VERIFICATION,
            }
        ],
    )

    rc = podium.main(
        [
            "issues",
            "sync-from-github",
            "--cwd",
            str(repo),
            "--bindings",
            str(bindings),
            "--dry-run",
        ]
    )
    assert rc == 0


def test_cli_sync_from_github_no_binding_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    other = tmp_path / "elsewhere"
    other.mkdir()
    repo = _make_repo(tmp_path)
    _init_git_repo(repo, "git@github-personal:owner/repo.git")
    bindings = _make_bindings(tmp_path, repo)
    _init_db(tmp_path, monkeypatch)

    rc = podium.main(
        [
            "issues",
            "sync-from-github",
            "--cwd",
            str(other),
            "--bindings",
            str(bindings),
        ]
    )
    assert rc == 1
    assert "no podium binding matches" in capsys.readouterr().err


# --- pure helpers ---


@pytest.mark.parametrize(
    "body, expected",
    [
        ("## Parent\n\n#1 — Spec\n", True),
        ("## Parent\n\nshreeve1/repo#1 — Spec\n", True),
        ("## Parent\n\nNone\n", False),  # to-tickets no-parent marker
        ("## Other\n\n#1\n", False),  # no Parent heading
        ("", False),
    ],
)
def test_has_parent_section(body: str, expected: bool) -> None:
    assert podium_issues._has_parent_section(body) is expected


def test_extract_blocked_by_numbers_handles_section_and_dedup() -> None:
    body = (
        "## What to build\n\nignored #5 here.\n\n"
        "## Blocked by\n\n"
        "- #1 — Blocker one\n"
        "- shreeve1/repo#2 — Cross-repo\n"
        "- #1 — Duplicate\n"
        "\n## Acceptance\n\n- [ ] x\n"
    )
    assert podium_issues._extract_blocked_by_numbers(body) == [1, 2]


def test_extract_blocked_by_numbers_returns_empty_without_section() -> None:
    body = "## What to build\n\nRefs #5 but no Blocked-by section.\n"
    assert podium_issues._extract_blocked_by_numbers(body) == []
