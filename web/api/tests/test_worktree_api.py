"""API-level tests for worktree merge-on-done and toggle-off archive.

Each test creates a fresh git repo, seeds a podium.db, and patches issues
through the FastAPI TestClient.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import web.api.main as main
from web.api.tests.conftest import login

app = main.app


def _init_repo(path: Path) -> None:
    """Create a git repo at ``path`` with an initial commit on ``main``."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "test@test")
    _git(path, "config", "user.name", "Test")
    readme = path / "README.md"
    readme.write_text("# test", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "initial")


def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )


def _seed_podium(db_path: Path, binding_name: str = "trading") -> dict:
    """Seed podium.db with a binding and a todo issue. Returns the issue row."""
    import sqlite3

    from web.api.schema import SCHEMA_SQL

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA_SQL)
        conn.execute("INSERT INTO binding(name) VALUES (?)", (binding_name,))
        conn.execute(
            "INSERT INTO skill(name, description, source) VALUES ('/dev-build', '', 'test')"
        )
        cursor = conn.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, preferred_agent,
              preferred_skill, worktree_active, base_branch, comments_md, context_md,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', '', '2026-06-11T00:00:00+00:00', '2026-06-11T00:00:00+00:00')
            """,
            (
                binding_name,
                "Worktree test",
                "Test merge-on-done",
                "todo",
                "pi",
                "/dev-build",
                True,
                "main",
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM issue WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        assert row is not None
        return dict(row)
    finally:
        conn.close()


# Monkey-patch _load_bindings to return our test binding's repo path.
# We do this at module level via a fixture that overrides the bindings.yml source.


def _binding_entry(name: str, repo_path: Path) -> dict:
    return {
        "name": name,
        "plane_project_id": "fake-project",
        "repo_path": str(repo_path),
        "base_branch": "main",
        "default_agent": "pi",
        "type": "coding",
        "tracker": "podium",
    }


@pytest.fixture
def repo_and_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Create a git repo and a podium.db, wire them via _bindings_override."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    # Use _bindings_override so _repo_path_for_binding finds our test repo.
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("trading", repo)])
    return repo, db_path


@pytest.fixture(autouse=True)
def _clear_global_state():
    """Reset the module-level websocket hub between tests."""
    main.websocket_hub._subscribers.clear()
    main._bindings_override = None
    yield
    main.websocket_hub._subscribers.clear()
    main._bindings_override = None


# --- merge-on-done tests ---


def test_merge_on_done_happy_path(repo_and_db: tuple[Path, Path]) -> None:
    """State→done with worktree_active=true: creates worktree, commits, merges."""
    repo, db_path = repo_and_db
    from web.api.worktree import branch_name, create_worktree

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]
    issue_str = str(issue_id)

    # Create a worktree and make a commit (simulating agent work).
    wt_path = create_worktree(repo, "trading", issue_str, "main")
    (wt_path / "feature.txt").write_text("agent work", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "agent change")

    with TestClient(app) as client:
        login(client)
        response = client.patch(
            f"/api/issues/{issue_id}",
            json={"state": "done"},
        )
    body = response.json()
    assert response.status_code == 200, f"status={response.status_code} body={body}"
    assert body["state"] == "done", f"Blocked comment: {body.get('comments_md', '')}"
    assert body["worktree_path"] == f"worktrees/trading/{issue_id}"
    assert body["worktree_branch"] == f"podium/trading/{issue_id}"

    # The merge landed the agent commit.
    log = _git(repo, "log", "--oneline", "-1").stdout
    assert "agent change" in log

    # Worktree was cleaned up.
    assert not wt_path.is_dir()
    branches = _git(repo, "branch", "--list").stdout
    assert branch_name("trading", issue_str) not in branches


def test_merge_on_done_aborts_when_base_dirty(repo_and_db: tuple[Path, Path]) -> None:
    """Dirty base checkout aborts merge, issue becomes blocked."""
    repo, db_path = repo_and_db
    from web.api.worktree import create_worktree

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]

    wt_path = create_worktree(repo, "trading", str(issue_id), "main")
    (wt_path / "feature.txt").write_text("agent work", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "agent change")

    # Dirty the base repo by modifying a tracked file.
    (repo / "README.md").write_text("uncommitted change", encoding="utf-8")

    queue = main.websocket_hub.subscribe()
    try:
        with TestClient(app) as client:
            login(client)
            response = client.patch(
                f"/api/issues/{issue_id}",
                json={"state": "done"},
            )
    finally:
        main.websocket_hub.unsubscribe(queue)
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "blocked"
    assert "uncommitted changes" in body["comments_md"]

    messages = []
    while not queue.empty():
        messages.append(queue.get_nowait())
    assert messages[-1]["row"]["state"] == "blocked"

    # Worktree intact.
    assert wt_path.is_dir()


def test_combined_done_and_worktree_off_does_not_archive_after_merge_block(
    repo_and_db: tuple[Path, Path],
) -> None:
    """Merge/block result wins over archive note in a combined PATCH."""
    repo, db_path = repo_and_db
    from web.api.worktree import create_worktree

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]
    wt_path = create_worktree(repo, "trading", str(issue_id), "main")
    (wt_path / "feature.txt").write_text("agent work", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "agent change")
    (repo / "README.md").write_text("uncommitted change", encoding="utf-8")

    with TestClient(app) as client:
        login(client)
        response = client.patch(
            f"/api/issues/{issue_id}",
            json={
                "state": "done",
                "worktree_active": False,
                "comments_md": "operator note",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "blocked"
    assert "operator note" in body["comments_md"]
    assert "uncommitted changes" in body["comments_md"]
    assert "Worktree archived" not in body["comments_md"]
    assert wt_path.is_dir()


def test_merge_on_done_aborts_on_conflict(repo_and_db: tuple[Path, Path]) -> None:
    """Diverged base (commit on main after worktree creation) halts merge."""
    repo, db_path = repo_and_db
    from web.api.worktree import create_worktree

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]

    wt_path = create_worktree(repo, "trading", str(issue_id), "main")
    (wt_path / "feature.txt").write_text("agent work", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "agent change")

    # Commit on main (diverges from worktree branch).
    (repo / "main-edit.txt").write_text("main work", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "main edit")

    with TestClient(app) as client:
        login(client)
        response = client.patch(
            f"/api/issues/{issue_id}",
            json={"state": "done"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "blocked"
    assert "Auto-merge halted" in body["comments_md"]

    # Worktree intact.
    assert wt_path.is_dir()


def test_merge_on_done_aborts_on_force_pushed_base(
    repo_and_db: tuple[Path, Path],
) -> None:
    """Rewritten base history halts merge and leaves the worktree intact."""
    repo, db_path = repo_and_db
    from web.api.worktree import create_worktree

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]

    wt_path = create_worktree(repo, "trading", str(issue_id), "main")
    (wt_path / "feature.txt").write_text("agent work", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "agent change")

    _git(repo, "checkout", "--orphan", "rewritten-main")
    for path in repo.iterdir():
        if path.name in {".git", "worktrees"}:
            continue
        if path.is_dir():
            import shutil

            shutil.rmtree(path)
        else:
            path.unlink()
    (repo / "README.md").write_text("rewritten history", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "force-pushed replacement")
    _git(repo, "branch", "-M", "rewritten-main", "main")

    with TestClient(app) as client:
        login(client)
        response = client.patch(
            f"/api/issues/{issue_id}",
            json={"state": "done"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "blocked"
    assert "Auto-merge halted" in body["comments_md"]
    assert wt_path.is_dir()


def test_merge_on_done_noop_when_no_worktree(repo_and_db: tuple[Path, Path]) -> None:
    """State→done without a worktree is a clean transition."""
    db_path = repo_and_db[1]
    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]

    with TestClient(app) as client:
        login(client)
        response = client.patch(
            f"/api/issues/{issue_id}",
            json={"state": "done"},
        )
    assert response.status_code == 200
    assert response.json()["state"] == "done"


# --- archive teardown tests ---


def test_archive_idle_issue_removes_worktree_and_branch(
    repo_and_db: tuple[Path, Path],
) -> None:
    """State→archived with no active run tears down persistent worktree."""
    repo, db_path = repo_and_db
    from web.api.worktree import branch_name, create_worktree, worktree_dir

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]
    issue_str = str(issue_id)
    create_worktree(repo, "trading", issue_str, "main")

    with TestClient(app) as client:
        login(client)
        response = client.patch(
            f"/api/issues/{issue_id}",
            json={"state": "archived"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "archived"
    assert body["worktree_active"] is False
    assert not worktree_dir(repo, "trading", issue_str).is_dir()
    branches = _git(repo, "branch", "--list").stdout
    assert branch_name("trading", issue_str) not in branches


def test_archive_active_issue_leaves_worktree_until_run_completion(
    repo_and_db: tuple[Path, Path],
) -> None:
    """State→archived during queued/running run leaves live worktree intact."""
    repo, db_path = repo_and_db
    from web.api.worktree import branch_name, create_worktree, worktree_dir

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]
    issue_str = str(issue_id)
    create_worktree(repo, "trading", issue_str, "main")
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE issue SET latest_run_state = 'running' WHERE id = ?",
            (issue_id,),
        )
        conn.commit()

    with TestClient(app) as client:
        login(client)
        response = client.patch(
            f"/api/issues/{issue_id}",
            json={"state": "archived"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "archived"
    assert body["worktree_active"] is True
    assert worktree_dir(repo, "trading", issue_str).is_dir()
    branches = _git(repo, "branch", "--list").stdout
    assert branch_name("trading", issue_str) in branches


# --- toggle-off archive tests ---


def test_toggle_worktree_off_archives_with_comment(
    repo_and_db: tuple[Path, Path],
) -> None:
    """Toggling worktree_active off while worktree exists appends archive note."""
    repo, db_path = repo_and_db
    from web.api.worktree import create_worktree

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]

    # Create a worktree.
    create_worktree(repo, "trading", str(issue_id), "main")

    with TestClient(app) as client:
        login(client)
        response = client.patch(
            f"/api/issues/{issue_id}",
            json={"worktree_active": False},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["worktree_active"] is False
    assert "Worktree archived" in body["comments_md"]

    # Worktree still on disk.
    from web.api.worktree import worktree_dir

    assert worktree_dir(repo, "trading", str(issue_id)).is_dir()


def test_toggle_worktree_off_no_worktree_no_comment(
    repo_and_db: tuple[Path, Path],
) -> None:
    """Toggling off without a worktree does not append an archive note."""
    db_path = repo_and_db[1]
    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]

    with TestClient(app) as client:
        login(client)
        response = client.patch(
            f"/api/issues/{issue_id}",
            json={"worktree_active": False},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["worktree_active"] is False
    # No archive comment because no worktree existed.
    assert "Worktree archived" not in (body["comments_md"] or "")
