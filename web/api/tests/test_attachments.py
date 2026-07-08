"""Tests for issue attachment API endpoints and purge lifecycle (#323).

Covers upload, list, download, delete, unknown issue, wrong attachment id,
empty and oversized upload, binary roundtrip, and local purge behavior.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import web.api.main as main
from web.api.tests.conftest import login

app = main.app


def _init_repo(path: Path) -> None:
    """Create a git repo at ``path`` with an initial commit on ``main``."""
    path.mkdir(parents=True, exist_ok=True)
    for cmd in (
        ("init", "-b", "main"),
        ("config", "user.email", "test@test"),
        ("config", "user.name", "Test"),
    ):
        main.subprocess.run(
            ["git", "-C", str(path), *cmd],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
    readme = path / "README.md"
    readme.write_text("# test", encoding="utf-8")
    main.subprocess.run(
        ["git", "-C", str(path), "add", "."],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    main.subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "initial"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )


def _binding_entry(name: str, repo_path: Path) -> dict:
    return {
        "name": name,
        "repo_path": str(repo_path),
        "base_branch": "main",
        "default_agent": "pi",
        "type": "coding",
        "tracker": "podium",
    }


def _seed_binding(db_path: Path, name: str = "trading") -> None:
    conn = main.connect(db_path)
    try:
        main.ensure_schema(conn)
        conn.execute(
            "INSERT OR IGNORE INTO binding(name, display_name, sort_order) "
            "VALUES (?, ?, 0)",
            (name, name),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def _clear_global_state():
    main.websocket_hub._subscribers.clear()
    main._bindings_override = None
    yield
    main.websocket_hub._subscribers.clear()
    main._bindings_override = None


@pytest.fixture
def db_and_client(monkeypatch, tmp_path: Path) -> Iterator[tuple[Path, TestClient]]:
    """A podium.db with binding + one issue, using a real git repo."""
    db_path = tmp_path / "podium.db"
    repo = tmp_path / "repo"
    _init_repo(repo)
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("trading", repo)])
    _seed_binding(db_path)

    with TestClient(app) as client:
        login(client)
        resp = client.post(
            "/api/bindings/trading/issues", json={"description": "test issue"}
        )
        assert resp.status_code == 201
        yield db_path, client


# ──────────────── upload ────────────────


def test_upload_attachment(db_and_client: tuple[Path, TestClient]) -> None:
    db_path, client = db_and_client
    issue_id = _first_issue_id(client)

    resp = client.post(
        f"/api/issues/{issue_id}/attachments",
        files={"file": ("hello.txt", b"hello world", "text/plain")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["display_name"] == "hello.txt"
    assert data["content_type"] == "text/plain"
    assert data["size_bytes"] == 11
    assert data["issue_id"] == issue_id

    # File exists on disk
    repo = db_path.parent / "repo"
    stored = data["stored_name"]
    path = repo / ".symphony" / "attachments" / str(issue_id) / stored
    assert path.read_bytes() == b"hello world"


def test_upload_empty_file_rejected(db_and_client: tuple[Path, TestClient]) -> None:
    _, client = db_and_client
    issue_id = _first_issue_id(client)

    resp = client.post(
        f"/api/issues/{issue_id}/attachments",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


def test_upload_oversized_rejected(db_and_client: tuple[Path, TestClient]) -> None:
    _, client = db_and_client
    issue_id = _first_issue_id(client)
    big = b"x" * (main._attachments.MAX_UPLOAD_BYTES + 1)

    resp = client.post(
        f"/api/issues/{issue_id}/attachments",
        files={"file": ("big.bin", big, "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "exceeds" in resp.json()["detail"].lower()


def test_upload_unknown_issue(db_and_client: tuple[Path, TestClient]) -> None:
    _, client = db_and_client

    resp = client.post(
        "/api/issues/99999/attachments",
        files={"file": ("x.txt", b"x", "text/plain")},
    )
    assert resp.status_code == 404


def test_upload_invalid_display_name(db_and_client: tuple[Path, TestClient]) -> None:
    _, client = db_and_client
    issue_id = _first_issue_id(client)

    resp = client.post(
        f"/api/issues/{issue_id}/attachments",
        files={"file": ("/", b"x", "text/plain")},
    )
    assert resp.status_code == 400


# ──────────────── list ────────────────


def test_list_attachments(db_and_client: tuple[Path, TestClient]) -> None:
    _, client = db_and_client
    issue_id = _first_issue_id(client)

    # Upload two attachments
    client.post(
        f"/api/issues/{issue_id}/attachments",
        files={"file": ("a.txt", b"aaa", "text/plain")},
    )
    client.post(
        f"/api/issues/{issue_id}/attachments",
        files={"file": ("b.txt", b"bbb", "text/plain")},
    )

    resp = client.get(f"/api/issues/{issue_id}/attachments")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # Metadata only — no stored_name in list response
    for item in data:
        assert "display_name" in item
        assert "content_type" in item
        assert "size_bytes" in item
        assert "stored_name" not in item


def test_list_attachments_empty_issue(db_and_client: tuple[Path, TestClient]) -> None:
    _, client = db_and_client
    issue_id = _first_issue_id(client)

    resp = client.get(f"/api/issues/{issue_id}/attachments")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_attachments_unknown_issue(db_and_client: tuple[Path, TestClient]) -> None:
    _, client = db_and_client

    resp = client.get("/api/issues/99999/attachments")
    assert resp.status_code == 404


# ──────────────── download ────────────────


def test_download_attachment(db_and_client: tuple[Path, TestClient]) -> None:
    _, client = db_and_client
    issue_id = _first_issue_id(client)

    resp = client.post(
        f"/api/issues/{issue_id}/attachments",
        files={"file": ("hello.txt", b"hello world", "text/plain")},
    )
    attachment_id = resp.json()["id"]

    dl = client.get(f"/api/issues/{issue_id}/attachments/{attachment_id}")
    assert dl.status_code == 200
    assert dl.content == b"hello world"
    assert dl.headers["content-type"] == "text/plain; charset=utf-8"
    assert 'filename="hello.txt"' in dl.headers["content-disposition"]


def test_download_binary_roundtrip(db_and_client: tuple[Path, TestClient]) -> None:
    """Upload binary data, download it, verify exact roundtrip."""
    _, client = db_and_client
    issue_id = _first_issue_id(client)
    payload = bytes(range(256))  # 0-255

    resp = client.post(
        f"/api/issues/{issue_id}/attachments",
        files={"file": ("binary.bin", payload, "application/octet-stream")},
    )
    attachment_id = resp.json()["id"]

    dl = client.get(f"/api/issues/{issue_id}/attachments/{attachment_id}")
    assert dl.status_code == 200
    assert dl.content == payload


def test_download_wrong_attachment_id(db_and_client: tuple[Path, TestClient]) -> None:
    _, client = db_and_client
    issue_id = _first_issue_id(client)

    resp = client.get(f"/api/issues/{issue_id}/attachments/99999")
    assert resp.status_code == 404


def test_download_attachment_wrong_issue(
    db_and_client: tuple[Path, TestClient],
) -> None:
    _, client = db_and_client
    issue_id = _first_issue_id(client)

    # Upload to issue A
    resp = client.post(
        f"/api/issues/{issue_id}/attachments",
        files={"file": ("x.txt", b"x", "text/plain")},
    )
    attachment_id = resp.json()["id"]

    # Create a second issue
    resp2 = client.post(
        "/api/bindings/trading/issues", json={"description": "second issue"}
    )
    issue_id_2 = resp2.json()["id"]

    # Try to download attachment_id from issue B — should 404
    dl = client.get(f"/api/issues/{issue_id_2}/attachments/{attachment_id}")
    assert dl.status_code == 404


# ──────────────── delete ────────────────


def test_delete_attachment(db_and_client: tuple[Path, TestClient]) -> None:
    db_path, client = db_and_client
    issue_id = _first_issue_id(client)

    resp = client.post(
        f"/api/issues/{issue_id}/attachments",
        files={"file": ("del.txt", b"to delete", "text/plain")},
    )
    data = resp.json()
    attachment_id = data["id"]
    stored_name = data["stored_name"]

    dl = client.delete(f"/api/issues/{issue_id}/attachments/{attachment_id}")
    assert dl.status_code == 200
    assert dl.json() == {"deleted": True}

    # Gone from list
    list_resp = client.get(f"/api/issues/{issue_id}/attachments")
    assert list_resp.json() == []

    # File removed from disk
    repo = db_path.parent / "repo"
    path = repo / ".symphony" / "attachments" / str(issue_id) / stored_name
    assert not path.exists()


def test_delete_missing_file_tolerated(
    db_and_client: tuple[Path, TestClient],
) -> None:
    """Delete tolerates missing file on disk — DB row still removed."""
    db_path, client = db_and_client
    issue_id = _first_issue_id(client)

    resp = client.post(
        f"/api/issues/{issue_id}/attachments",
        files={"file": ("gone.txt", b"will vanish", "text/plain")},
    )
    data = resp.json()
    attachment_id = data["id"]
    stored_name = data["stored_name"]

    # Remove the file manually
    repo = db_path.parent / "repo"
    path = repo / ".symphony" / "attachments" / str(issue_id) / stored_name
    path.unlink()

    dl = client.delete(f"/api/issues/{issue_id}/attachments/{attachment_id}")
    assert dl.status_code == 200
    assert dl.json() == {"deleted": True}

    # DB row gone
    list_resp = client.get(f"/api/issues/{issue_id}/attachments")
    assert list_resp.json() == []


def test_delete_wrong_attachment_id(
    db_and_client: tuple[Path, TestClient],
) -> None:
    _, client = db_and_client
    issue_id = _first_issue_id(client)

    resp = client.delete(f"/api/issues/{issue_id}/attachments/99999")
    assert resp.status_code == 404


def test_delete_attachment_wrong_issue(
    db_and_client: tuple[Path, TestClient],
) -> None:
    """Can't delete an attachment through a different issue's endpoint."""
    _, client = db_and_client
    issue_id = _first_issue_id(client)

    resp = client.post(
        f"/api/issues/{issue_id}/attachments",
        files={"file": ("x.txt", b"x", "text/plain")},
    )
    attachment_id = resp.json()["id"]

    # Create second issue
    resp2 = client.post(
        "/api/bindings/trading/issues", json={"description": "second issue"}
    )
    issue_id_2 = resp2.json()["id"]

    dl = client.delete(f"/api/issues/{issue_id_2}/attachments/{attachment_id}")
    assert dl.status_code == 404


# ──────────────── purge ────────────────


def test_archive_purge_removes_attachments(
    monkeypatch, tmp_path: Path
) -> None:
    """Purge removes attachment rows (CASCADE) and best-effort files."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("trading", repo)])
    _seed_binding(db_path)

    conn = main.connect(db_path)
    try:
        days_ago = 20
        updated_at = (
            datetime.now(UTC) - timedelta(days=days_ago)
        ).isoformat()
        created_at = (
            datetime.now(UTC) - timedelta(days=days_ago + 1)
        ).isoformat()
        cursor = conn.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, priority, worktree_active,
              base_branch, comments_md, context_md, created_at, updated_at
            ) VALUES (?, ?, '', 'archived', 'med', FALSE, 'main', '', '', ?, ?)
            """,
            ("trading", f"purge-att-{days_ago}d", created_at, updated_at),
        )
        issue_id = int(cursor.lastrowid)

        # Insert two attachments
        stored_names = []
        for i in range(2):
            stored_name = f"abc{i:032x}"
            stored_names.append(stored_name)
            conn.execute(
                """
                INSERT INTO issue_attachment(
                  issue_id, display_name, stored_name, content_type,
                  size_bytes, storage_rel_path, created_at
                ) VALUES (?, ?, ?, 'text/plain', 4, ?, ?)
                """,
                (
                    issue_id,
                    f"file{i}.txt",
                    stored_name,
                    f".symphony/attachments/{issue_id}/{stored_name}",
                    created_at,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    # Create attachment files on disk
    att_dir = repo / ".symphony" / "attachments" / str(issue_id)
    att_dir.mkdir(parents=True)
    for sn in stored_names:
        (att_dir / sn).write_bytes(b"data")

    # Startup purge via TestClient lifespan
    with TestClient(app):
        login(TestClient(app))

    # DB rows gone (CASCADE via issue delete)
    conn2 = main.connect(db_path)
    try:
        count = conn2.execute(
            "SELECT COUNT(*) FROM issue_attachment WHERE issue_id = ?",
            (issue_id,),
        ).fetchone()[0]
        assert count == 0
    finally:
        conn2.close()

    # Attachment files best-effort deleted
    for sn in stored_names:
        assert not (att_dir / sn).exists()


def test_archive_purge_missing_attachment_file_not_abort(
    monkeypatch, tmp_path: Path
) -> None:
    """Purge continues when an attachment file is already missing."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("trading", repo)])
    _seed_binding(db_path)

    conn = main.connect(db_path)
    try:
        days_ago = 20
        updated_at = (
            datetime.now(UTC) - timedelta(days=days_ago)
        ).isoformat()
        created_at = (
            datetime.now(UTC) - timedelta(days=days_ago + 1)
        ).isoformat()
        cursor = conn.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, priority, worktree_active,
              base_branch, comments_md, context_md, created_at, updated_at
            ) VALUES (?, ?, '', 'archived', 'med', FALSE, 'main', '', '', ?, ?)
            """,
            ("trading", f"purge-att-missing-{days_ago}d", created_at, updated_at),
        )
        issue_id = int(cursor.lastrowid)

        # Insert attachment row but DON'T create the file on disk
        conn.execute(
            """
            INSERT INTO issue_attachment(
              issue_id, display_name, stored_name, content_type,
              size_bytes, storage_rel_path, created_at
            ) VALUES (?, 'ghost.txt', 'ghost_stored', 'text/plain', 4, ?, ?)
            """,
            (
                issue_id,
                f".symphony/attachments/{issue_id}/ghost_stored",
                created_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # Purge should not fail
    with TestClient(app):
        login(TestClient(app))

    conn2 = main.connect(db_path)
    try:
        count = conn2.execute(
            "SELECT COUNT(*) FROM issue_attachment WHERE issue_id = ?",
            (issue_id,),
        ).fetchone()[0]
        assert count == 0
    finally:
        conn2.close()


def test_archive_purge_rollback_preserves_attachments(
    monkeypatch, tmp_path: Path
) -> None:
    """A mid-purge failure rolls back, preserving attachment rows and files."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("trading", repo)])
    _seed_binding(db_path)

    conn = main.connect(db_path)
    try:
        days_ago = 20
        updated_at = (
            datetime.now(UTC) - timedelta(days=days_ago)
        ).isoformat()
        created_at = (
            datetime.now(UTC) - timedelta(days=days_ago + 1)
        ).isoformat()
        cursor = conn.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, priority, worktree_active,
              base_branch, comments_md, context_md, created_at, updated_at
            ) VALUES (?, ?, '', 'archived', 'med', FALSE, 'main', '', '', ?, ?)
            """,
            ("trading", f"purge-rollback-{days_ago}d", created_at, updated_at),
        )
        issue_id = int(cursor.lastrowid)

        stored_name = "rollback_stored"
        conn.execute(
            """
            INSERT INTO issue_attachment(
              issue_id, display_name, stored_name, content_type,
              size_bytes, storage_rel_path, created_at
            ) VALUES (?, 'keep.txt', ?, 'text/plain', 3, ?, ?)
            """,
            (
                issue_id,
                stored_name,
                f".symphony/attachments/{issue_id}/{stored_name}",
                created_at,
            ),
        )

        # Create a foreign-key reference to block issue deletion
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _purge_test_ref("
            "  id INTEGER PRIMARY KEY,"
            "  issue_id INTEGER REFERENCES issue(id)"
            ")"
        )
        conn.execute("INSERT INTO _purge_test_ref(issue_id) VALUES (?)", (issue_id,))
        conn.commit()
    finally:
        conn.close()

    # Create file on disk
    att_dir = repo / ".symphony" / "attachments" / str(issue_id)
    att_dir.mkdir(parents=True)
    (att_dir / stored_name).write_bytes(b"abc")

    with TestClient(app):
        login(TestClient(app))

    # Rollback preserved everything
    conn2 = main.connect(db_path)
    try:
        issue_count = conn2.execute(
            "SELECT COUNT(*) FROM issue WHERE id = ?", (issue_id,)
        ).fetchone()[0]
        assert issue_count == 1
        att_count = conn2.execute(
            "SELECT COUNT(*) FROM issue_attachment WHERE issue_id = ?",
            (issue_id,),
        ).fetchone()[0]
        assert att_count == 1
    finally:
        conn2.close()

    # File still there
    assert (att_dir / stored_name).read_bytes() == b"abc"

    # Cleanup
    conn3 = main.connect(db_path)
    try:
        conn3.execute("DROP TABLE IF EXISTS _purge_test_ref")
        conn3.commit()
    finally:
        conn3.close()


# ──────────────── helpers ────────────────


def _first_issue_id(client: TestClient) -> int:
    issues = client.get("/api/bindings/trading/issues").json()
    return issues[0]["id"]
