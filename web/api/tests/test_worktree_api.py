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


def _remote_binding_entry(name: str) -> dict:
    """Remote binding (ADR-0012): repo_path is on another host. Any local git
    or Path op against it would fail — the guards must skip them."""
    return {
        "name": name,
        "repo_path": "/home/itadmin/itastack",
        "base_branch": "main",
        "default_agent": "pi",
        "type": "coding",
        "pi_mode": "one-shot",
        "tracker": "podium",
        "remote": {"user": "itadmin", "host": "100.95.224.218"},
    }


@pytest.fixture
def remote_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Seed a podium.db for a remote binding via _bindings_override (no repo)."""
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(main, "_bindings_override", [_remote_binding_entry("n8n")])
    return db_path


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
    assert body["worktree_active"] is False

    # The merge landed the agent commit.
    log = _git(repo, "log", "--oneline", "-1").stdout
    assert "agent change" in log

    # Worktree was cleaned up.
    assert not wt_path.is_dir()
    branches = _git(repo, "branch", "--list").stdout
    assert branch_name("trading", issue_str) not in branches


def test_merge_on_done_stashes_dirty_base_and_issue_wins(
    repo_and_db: tuple[Path, Path],
) -> None:
    """Dirty base WIP no longer blocks; issue branch wins overlap."""
    repo, db_path = repo_and_db
    from web.api.worktree import create_worktree

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]

    wt_path = create_worktree(repo, "trading", str(issue_id), "main")
    (wt_path / "README.md").write_text("agent version", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "agent change")

    # Dirty the base repo with overlapping WIP plus a non-conflicting file.
    (repo / "README.md").write_text("operator WIP", encoding="utf-8")
    (repo / "operator.txt").write_text("keep me", encoding="utf-8")

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
    assert body["state"] == "done"
    assert body["worktree_active"] is False

    messages = []
    while not queue.empty():
        messages.append(queue.get_nowait())
    assert messages[-1]["row"]["state"] == "done"

    assert not wt_path.is_dir()
    assert (repo / "README.md").read_text(encoding="utf-8") == "agent version"
    assert (repo / "operator.txt").read_text(encoding="utf-8") == "keep me"


def test_combined_done_and_worktree_off_does_not_archive_after_dirty_base_land(
    repo_and_db: tuple[Path, Path],
) -> None:
    """Merge result wins over archive note in a combined PATCH."""
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
    assert body["state"] == "done"
    assert "operator note" in body["comments_md"]
    assert "Worktree archived" not in body["comments_md"]
    assert not wt_path.is_dir()
    assert body["worktree_active"] is False


def test_merge_on_done_rebases_non_conflicting_diverged_base(
    repo_and_db: tuple[Path, Path],
) -> None:
    """Diverged base with non-overlapping edits rebases, merges, and cleans up."""
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
    assert body["state"] == "done"

    # Worktree cleaned up after successful rebase retry.
    assert not wt_path.exists()


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


def test_done_missing_worktree_blocks(repo_and_db: tuple[Path, Path]) -> None:
    """worktree_active set but worktree absent → block, never a false done
    (finding #1 missing-worktree case). worktree_active left unchanged."""
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
    body = response.json()
    assert body["state"] == "blocked"
    assert "cannot prove landing" in body["comments_md"]
    assert body["worktree_active"] is True


# --- dirty-worktree commit re-dispatch tests (ADR-0014) ---


def _set_comments_md(db_path: Path, issue_id: int, comments_md: str) -> None:
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE issue SET comments_md = ? WHERE id = ?", (comments_md, issue_id)
        )
        conn.commit()


def test_done_dirty_worktree_redispatches_to_commit(
    repo_and_db: tuple[Path, Path],
) -> None:
    """Dirty worktree, no prior marker → state=todo, synthetic note appended,
    worktree + branch intact, base branch NOT advanced."""
    repo, db_path = repo_and_db
    from web.api.worktree import branch_name, create_worktree

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]
    issue_str = str(issue_id)

    wt_path = create_worktree(repo, "trading", issue_str, "main")
    # Uncommitted agent output (untracked) — dirty worktree, no commits ahead.
    (wt_path / "feature.txt").write_text("agent work", encoding="utf-8")

    base_head_before = _git(repo, "rev-parse", "HEAD").stdout.strip()

    with TestClient(app) as client:
        login(client)
        response = client.patch(f"/api/issues/{issue_id}", json={"state": "done"})
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["state"] == "todo"
    assert main.COMMIT_REDISPATCH_REPLY_PREFIX in body["comments_md"]
    assert main.OPERATOR_RELAND_PENDING_PREFIX in body["comments_md"]

    # Worktree + branch left intact; base branch not advanced.
    assert wt_path.is_dir()
    branches = _git(repo, "branch", "--list").stdout
    assert branch_name("trading", issue_str) in branches
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == base_head_before


def test_done_dirty_worktree_blocks_at_cap(
    repo_and_db: tuple[Path, Path],
) -> None:
    """Dirty worktree with MAX prior markers → state=blocked, worktree intact."""
    repo, db_path = repo_and_db
    from web.api.worktree import create_worktree

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]
    issue_str = str(issue_id)

    wt_path = create_worktree(repo, "trading", issue_str, "main")
    (wt_path / "feature.txt").write_text("agent work", encoding="utf-8")

    # Pre-seed comments_md with MAX_COMMIT_REDISPATCH prior markers.
    prior = "\n\n".join(
        f"{main.COMMIT_REDISPATCH_REPLY_PREFIX} · 2026-06-1{n})\n\nbody"
        for n in range(main.MAX_COMMIT_REDISPATCH)
    )
    _set_comments_md(db_path, issue_id, prior)

    with TestClient(app) as client:
        login(client)
        response = client.patch(f"/api/issues/{issue_id}", json={"state": "done"})
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["state"] == "blocked"
    assert "still" in body["comments_md"]
    assert str(main.MAX_COMMIT_REDISPATCH) in body["comments_md"]
    assert wt_path.is_dir()


def test_done_clean_worktree_no_commits_teardown_no_redispatch(
    repo_and_db: tuple[Path, Path],
) -> None:
    """Clean worktree, no commits ahead → no-op merge + teardown, stays done,
    no re-dispatch note (genuinely empty: nothing to lose)."""
    repo, db_path = repo_and_db
    from web.api.worktree import worktree_dir

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]
    issue_str = str(issue_id)

    from web.api.worktree import create_worktree

    create_worktree(repo, "trading", issue_str, "main")  # clean, no edits

    with TestClient(app) as client:
        login(client)
        response = client.patch(f"/api/issues/{issue_id}", json={"state": "done"})
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["state"] == "done"
    assert main.COMMIT_REDISPATCH_REPLY_PREFIX not in (body["comments_md"] or "")
    # Worktree torn down.
    assert not worktree_dir(repo, "trading", issue_str).is_dir()


def test_done_partial_commit_redispatches_not_partial_merge(
    repo_and_db: tuple[Path, Path],
) -> None:
    """One committed change ahead PLUS an uncommitted change → re-dispatch
    (state=todo), note appended, worktree + branch intact, base unchanged. The
    committed-ahead portion must NOT be partially merged."""
    repo, db_path = repo_and_db
    from web.api.worktree import branch_name, create_worktree

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]
    issue_str = str(issue_id)

    wt_path = create_worktree(repo, "trading", issue_str, "main")
    # One committed change ahead of base.
    (wt_path / "committed.txt").write_text("committed work", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "partial commit")
    # Plus an uncommitted change → worktree dirty.
    (wt_path / "uncommitted.txt").write_text("not yet committed", encoding="utf-8")

    base_head_before = _git(repo, "rev-parse", "HEAD").stdout.strip()

    with TestClient(app) as client:
        login(client)
        response = client.patch(f"/api/issues/{issue_id}", json={"state": "done"})
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["state"] == "todo"
    assert main.COMMIT_REDISPATCH_REPLY_PREFIX in body["comments_md"]
    # No partial merge: base branch unchanged, worktree + branch intact.
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == base_head_before
    assert wt_path.is_dir()
    branches = _git(repo, "branch", "--list").stdout
    assert branch_name("trading", issue_str) in branches


def test_redispatch_note_matches_operator_reply_regex(
    repo_and_db: tuple[Path, Path],
) -> None:
    """The synthetic note header matches prompt_renderer's operator-reply regex
    so it surfaces as the current request on resume, and is counted as one
    attempt by _count_commit_redispatches."""
    import prompt_renderer

    repo, db_path = repo_and_db
    from web.api.worktree import create_worktree

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]
    issue_str = str(issue_id)

    wt_path = create_worktree(repo, "trading", issue_str, "main")
    (wt_path / "feature.txt").write_text("agent work", encoding="utf-8")

    with TestClient(app) as client:
        login(client)
        response = client.patch(f"/api/issues/{issue_id}", json={"state": "done"})
    comments_md = response.json()["comments_md"]

    assert prompt_renderer._OPERATOR_REPLY_RE.search(comments_md) is not None
    assert main._count_commit_redispatches(comments_md) == 1


# --- land-on-done hardening: crash-safety, active-run guard, race abort ---


def test_done_worktree_not_persisted_before_merge(
    repo_and_db: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """done is not durable until the merge is proven (finding #1): if the land
    finalization crashes, the issue row stays in its pre-state, never done."""
    import contextlib
    import sqlite3

    repo, db_path = repo_and_db
    from web.api.worktree import create_worktree

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]
    issue_str = str(issue_id)
    wt_path = create_worktree(repo, "trading", issue_str, "main")
    (wt_path / "feature.txt").write_text("agent work", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "agent change")

    async def _boom(*_a, **_k):
        raise RuntimeError("crash after merge, before persisting done")

    monkeypatch.setattr(main, "_finalize_worktree_done", _boom)

    with TestClient(app) as client:
        login(client)
        with contextlib.suppress(Exception):
            client.patch(f"/api/issues/{issue_id}", json={"state": "done"})
    with sqlite3.connect(db_path) as conn:
        row_state = conn.execute(
            "SELECT state FROM issue WHERE id = ?", (issue_id,)
        ).fetchone()[0]
    assert row_state != "done", "done must not be durable before the merge is proven"


def test_done_rejected_during_active_run(
    repo_and_db: tuple[Path, Path],
) -> None:
    """An active run (queued/running) blocks move-to-done with 409 (finding #4)."""
    import sqlite3

    repo, db_path = repo_and_db
    from web.api.worktree import create_worktree

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]
    issue_str = str(issue_id)
    wt_path = create_worktree(repo, "trading", issue_str, "main")
    (wt_path / "feature.txt").write_text("agent work", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "agent change")

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE issue SET latest_run_state = 'running' WHERE id = ?", (issue_id,)
        )
        conn.commit()

    with TestClient(app) as client:
        login(client)
        response = client.patch(f"/api/issues/{issue_id}", json={"state": "done"})
    assert response.status_code == 409, response.text
    assert "land not allowed during active run" in response.json()["detail"]
    with sqlite3.connect(db_path) as conn:
        row_state = conn.execute(
            "SELECT state FROM issue WHERE id = ?", (issue_id,)
        ).fetchone()[0]
    assert row_state == "todo"
    assert wt_path.is_dir()


def test_land_aborts_if_run_starts_during_merge(
    repo_and_db: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run appearing between merge success and cleanup aborts the land to a
    recoverable in_review; worktree kept, cleanup NOT called (finding #4)."""
    import sqlite3

    import web.api.worktree as wt_mod

    repo, db_path = repo_and_db
    from web.api.worktree import create_worktree

    issue = _seed_podium(db_path, "trading")
    issue_id = issue["id"]
    issue_str = str(issue_id)
    wt_path = create_worktree(repo, "trading", issue_str, "main")
    (wt_path / "feature.txt").write_text("agent work", encoding="utf-8")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "agent change")

    real_merge = wt_mod.merge_worktree

    def fake_merge(repo_path, binding, iss, base):
        error = real_merge(repo_path, binding, iss, base)
        # A run starts mid-merge (after the branch is already on main).
        with sqlite3.connect(db_path) as c:
            c.execute(
                "UPDATE issue SET latest_run_state = 'running' WHERE id = ?",
                (issue_id,),
            )
            c.commit()
        return error

    monkeypatch.setattr(wt_mod, "merge_worktree", fake_merge)
    cleanup_calls: list[int] = []
    monkeypatch.setattr(
        wt_mod, "cleanup_worktree", lambda *a, **k: cleanup_calls.append(1)
    )

    with TestClient(app) as client:
        login(client)
        response = client.patch(f"/api/issues/{issue_id}", json={"state": "done"})
    body = response.json()
    assert body["state"] == "in_review", body.get("comments_md", "")
    assert "Aborted land" in body["comments_md"]
    assert wt_path.is_dir()
    assert cleanup_calls == []


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


# --- remote-binding worktree parity tests ---


def _no_local_worktree_ops(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every worktree helper blow up if a remote guard fails to skip it."""

    def _boom(*_a, **_k):
        raise AssertionError("local worktree op ran for a remote binding")

    import web.api.worktree as wt

    for fn in (
        "worktree_exists",
        "remove_worktree",
        "merge_worktree",
        "base_repo_dirty",
    ):
        monkeypatch.setattr(wt, fn, _boom)


def test_remote_done_merge_uses_remote_worktree_ops(
    remote_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_local_worktree_ops(monkeypatch)
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        "remote_worktree.worktree_exists",
        lambda remote, repo, binding, issue: (
            calls.append(("exists", binding, issue)) or True
        ),
    )
    monkeypatch.setattr(
        "remote_worktree.worktree_is_dirty",
        lambda remote, repo, binding, issue: (
            calls.append(("dirty", binding, issue)) and False
        ),
    )
    monkeypatch.setattr(
        "remote_worktree.base_repo_dirty",
        lambda remote, repo: calls.append(("base", "n8n", "")) and False,
    )
    monkeypatch.setattr(
        "remote_worktree.merge_worktree",
        lambda remote, repo, binding, issue, base: (
            calls.append(("merge", binding, issue)) or None
        ),
    )
    monkeypatch.setattr(
        "remote_worktree.remove_worktree",
        lambda remote, repo, binding, issue: calls.append(("remove", binding, issue)),
    )
    issue = _seed_podium(remote_db, "n8n")
    issue_id = issue["id"]

    with TestClient(app) as client:
        login(client)
        response = client.patch(f"/api/issues/{issue_id}", json={"state": "done"})
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["state"] == "done"
    assert body["worktree_active"] is False
    assert calls == [
        ("exists", "n8n", str(issue_id)),
        ("dirty", "n8n", str(issue_id)),
        ("base", "n8n", ""),
        ("merge", "n8n", str(issue_id)),
        ("remove", "n8n", str(issue_id)),
    ]


def test_remote_done_merge_blocks_on_dirty_remote_base(
    remote_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_local_worktree_ops(monkeypatch)
    monkeypatch.setattr("remote_worktree.worktree_exists", lambda *a: True)
    monkeypatch.setattr("remote_worktree.worktree_is_dirty", lambda *a: False)
    monkeypatch.setattr("remote_worktree.base_repo_dirty", lambda *a: True)
    monkeypatch.setattr(
        "remote_worktree.merge_worktree",
        lambda *a: pytest.fail("dirty remote base must not land"),
    )
    issue = _seed_podium(remote_db, "n8n")
    issue_id = issue["id"]

    with TestClient(app) as client:
        login(client)
        response = client.patch(f"/api/issues/{issue_id}", json={"state": "done"})

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["state"] == "blocked"
    assert "remote base checkout has uncommitted changes" in body["comments_md"]


def test_remote_land_aborts_if_run_starts_during_merge(
    remote_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remote split-land race: a run appearing mid-merge aborts to in_review,
    worktree kept, remote remove_worktree NOT called (finding #4)."""
    import sqlite3

    _no_local_worktree_ops(monkeypatch)
    monkeypatch.setattr("remote_worktree.worktree_exists", lambda *a: True)
    monkeypatch.setattr("remote_worktree.worktree_is_dirty", lambda *a: False)
    monkeypatch.setattr("remote_worktree.base_repo_dirty", lambda *a: False)

    issue = _seed_podium(remote_db, "n8n")
    issue_id = issue["id"]

    def _merge_starts_run(*_a, **_k):
        with sqlite3.connect(remote_db) as c:
            c.execute(
                "UPDATE issue SET latest_run_state = 'running' WHERE id = ?",
                (issue_id,),
            )
            c.commit()
        return None

    monkeypatch.setattr("remote_worktree.merge_worktree", _merge_starts_run)
    removed: list[int] = []
    monkeypatch.setattr(
        "remote_worktree.remove_worktree", lambda *_a, **_k: removed.append(1)
    )

    with TestClient(app) as client:
        login(client)
        response = client.patch(f"/api/issues/{issue_id}", json={"state": "done"})
    body = response.json()
    assert body["state"] == "in_review", body.get("comments_md", "")
    assert "Aborted land" in body["comments_md"]
    assert removed == []


def test_remote_archive_teardown_uses_remote_worktree_ops(
    remote_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_local_worktree_ops(monkeypatch)
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        "remote_worktree.worktree_exists",
        lambda remote, repo, binding, issue: (
            calls.append(("exists", binding, issue)) or True
        ),
    )
    monkeypatch.setattr(
        "remote_worktree.remove_worktree",
        lambda remote, repo, binding, issue: calls.append(("remove", binding, issue)),
    )
    issue = _seed_podium(remote_db, "n8n")
    issue_id = issue["id"]

    with TestClient(app) as client:
        login(client)
        response = client.patch(f"/api/issues/{issue_id}", json={"state": "archived"})
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["state"] == "archived"
    assert body["worktree_active"] is False
    assert calls == [("exists", "n8n", str(issue_id)), ("remove", "n8n", str(issue_id))]


def test_remote_toggle_off_archives_remote_worktree(
    remote_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_local_worktree_ops(monkeypatch)
    monkeypatch.setattr("remote_worktree.worktree_exists", lambda *a: True)
    issue = _seed_podium(remote_db, "n8n")
    issue_id = issue["id"]

    with TestClient(app) as client:
        login(client)
        response = client.patch(
            f"/api/issues/{issue_id}", json={"worktree_active": False}
        )
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["worktree_active"] is False
    assert "Worktree archived" in (body["comments_md"] or "")
