from __future__ import annotations

from collections.abc import Iterator
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from web.api.tests.conftest import login

main = cast(Any, import_module("web.api.main"))
app = cast(Any, main.app)


def _binding_entry(name: str, repo_path: Path) -> dict:
    return {
        "name": name,
        "base_branch": "main",
        "default_agent": "pi",
        "repo_path": str(repo_path),
    }


def _seed_binding_row(db_path: Path, name: str) -> None:
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
def _clear_override() -> Iterator[None]:
    main._bindings_override = None
    yield
    main._bindings_override = None


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A throwaway binding repo populated with sample files."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# hello\nsample editable file\n", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("ignored\n", encoding="utf-8")
    (root / "node_modules").mkdir()
    sub = root / "sub"
    sub.mkdir()
    (sub / "nested.py").write_text("print('hi')\n", encoding="utf-8")
    (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n binary")
    return root


@pytest.fixture()
def files_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path
) -> Iterator[TestClient]:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("demo", repo)])
    with TestClient(app) as client:
        login(client)
        _seed_binding_row(db_path, "demo")
        yield client


# ──────────────────────── listing ────────────────────────


def test_list_root_ignores_git_and_node_modules(files_client: TestClient) -> None:
    resp = files_client.get("/api/bindings/demo/files")
    assert resp.status_code == 200
    body = resp.json()
    assert body["path"] == ""
    names = {i["name"] for i in body["items"]}
    assert ".git" not in names
    assert "node_modules" not in names
    assert "README.md" in names
    assert "sub" in names
    # directories sorted first
    assert body["items"][0]["is_directory"] is True
    assert body["items"][0]["name"] == "sub"


def test_list_subdir(files_client: TestClient) -> None:
    resp = files_client.get("/api/bindings/demo/files", params={"path": "sub"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["path"] == "sub"
    items = {i["name"]: i for i in body["items"]}
    assert "nested.py" in items
    assert items["nested.py"]["path"] == "sub/nested.py"
    assert items["nested.py"]["is_directory"] is False


# ──────────────────────── read ────────────────────────


def test_read_editable_file(files_client: TestClient) -> None:
    resp = files_client.get(
        "/api/bindings/demo/files/content", params={"path": "README.md"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "# hello\nsample editable file\n"
    assert body["language"] == "markdown"
    assert body["editable"] is True
    assert body["size"] == len(body["content"].encode("utf-8"))
    assert isinstance(body["modified"], str)


def test_read_binary_rejected(files_client: TestClient) -> None:
    resp = files_client.get(
        "/api/bindings/demo/files/content", params={"path": "logo.png"}
    )
    assert resp.status_code == 400


def test_read_directory_rejected(files_client: TestClient) -> None:
    resp = files_client.get("/api/bindings/demo/files/content", params={"path": "sub"})
    assert resp.status_code == 400


def test_read_missing_404(files_client: TestClient) -> None:
    resp = files_client.get(
        "/api/bindings/demo/files/content", params={"path": "nope.md"}
    )
    assert resp.status_code == 404


def test_read_oversize_413(files_client: TestClient, repo: Path) -> None:
    big = repo / "big.txt"
    big.write_text("x" * (main._files.MAX_FILE_SIZE + 1), encoding="utf-8")
    resp = files_client.get(
        "/api/bindings/demo/files/content", params={"path": "big.txt"}
    )
    assert resp.status_code == 413


# ──────────────────────── write ────────────────────────


def test_write_roundtrip(files_client: TestClient, repo: Path) -> None:
    resp = files_client.put(
        "/api/bindings/demo/files/content",
        json={"path": "README.md", "content": "updated content\n"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "File saved"
    assert body["size"] == len("updated content\n".encode("utf-8"))
    assert (repo / "README.md").read_text(encoding="utf-8") == "updated content\n"
    # re-read via API
    re = files_client.get(
        "/api/bindings/demo/files/content", params={"path": "README.md"}
    )
    assert re.json()["content"] == "updated content\n"


def test_write_creates_parent_dirs(files_client: TestClient, repo: Path) -> None:
    resp = files_client.put(
        "/api/bindings/demo/files/content",
        json={"path": "a/b/c/new.txt", "content": "deep\n"},
    )
    assert resp.status_code == 200
    assert (repo / "a" / "b" / "c" / "new.txt").read_text(encoding="utf-8") == "deep\n"


def test_read_non_utf8_in_editable_extension_rejected(
    files_client: TestClient, repo: Path
) -> None:
    # Non-text bytes in an editable extension: extension-only binary check
    # passes, so read_text must catch UnicodeDecodeError and 400, not 500.
    (repo / "broken.txt").write_bytes(b"\xff\xfe\x00\x01not utf-8")
    resp = files_client.get(
        "/api/bindings/demo/files/content", params={"path": "broken.txt"}
    )
    assert resp.status_code == 400


def test_write_parent_is_existing_file_rejected(files_client: TestClient) -> None:
    # README.md is a file; writing "README.md/child.txt" must 400, not 500.
    resp = files_client.put(
        "/api/bindings/demo/files/content",
        json={"path": "README.md/child.txt", "content": "x"},
    )
    assert resp.status_code == 400


def test_write_non_editable_rejected(files_client: TestClient) -> None:
    resp = files_client.put(
        "/api/bindings/demo/files/content",
        json={"path": "evil.png", "content": "nope"},
    )
    assert resp.status_code == 400


# ──────────────────────── path safety ────────────────────────


def test_traversal_rejected(files_client: TestClient) -> None:
    resp = files_client.get(
        "/api/bindings/demo/files/content", params={"path": "../secret"}
    )
    assert resp.status_code == 403


def test_absolute_path_rejected(files_client: TestClient) -> None:
    resp = files_client.get(
        "/api/bindings/demo/files/content", params={"path": "/etc/passwd"}
    )
    assert resp.status_code == 403


def test_symlink_escape_rejected(files_client: TestClient, repo: Path) -> None:
    (repo / "escape").symlink_to("/etc")
    resp = files_client.get(
        "/api/bindings/demo/files/content", params={"path": "escape/hostname"}
    )
    assert resp.status_code == 403


# ──────────────────────── unknown binding ────────────────────────


def test_unknown_binding_list_404(files_client: TestClient) -> None:
    resp = files_client.get("/api/bindings/ghost/files")
    assert resp.status_code == 404


def test_unknown_binding_read_404(files_client: TestClient) -> None:
    resp = files_client.get(
        "/api/bindings/ghost/files/content", params={"path": "x.md"}
    )
    assert resp.status_code == 404


def test_unknown_binding_write_404(files_client: TestClient) -> None:
    resp = files_client.put(
        "/api/bindings/ghost/files/content",
        json={"path": "x.md", "content": "x"},
    )
    assert resp.status_code == 404


# ──────────────────────── override resolution ────────────────────────


def test_endpoint_honors_bindings_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Proves files._binding_repo_root reads live monkeypatched override
    via sys.modules under the pytest import path."""
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    other = tmp_path / "other_repo"
    other.mkdir()
    (other / "marker.md").write_text("override target\n", encoding="utf-8")
    monkeypatch.setattr(main, "_bindings_override", [_binding_entry("ov", other)])
    with TestClient(app) as client:
        login(client)
        _seed_binding_row(db_path, "ov")
        resp = client.get(
            "/api/bindings/ov/files/content", params={"path": "marker.md"}
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "override target\n"
