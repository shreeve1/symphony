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
