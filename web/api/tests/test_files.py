from __future__ import annotations

import base64
import json
import subprocess
import sys
from collections.abc import Iterator
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from web.api.tests.conftest import login

main = cast(Any, import_module("web.api.main"))
app = cast(Any, main.app)


def _binding_entry(
    name: str, repo_path: Path, *, remote: bool = False
) -> dict[str, Any]:
    binding: dict[str, Any] = {
        "name": name,
        "base_branch": "main",
        "default_agent": "pi",
        "repo_path": str(repo_path),
    }
    if remote:
        binding["remote"] = {"host": "remote.test", "user": "operator"}
    return binding


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


@pytest.fixture()
def remote_files_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[TestClient]:
    db_path = tmp_path / "podium.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(db_path))
    monkeypatch.setattr(
        main,
        "_bindings_override",
        [_binding_entry("remote", Path("/remote/repo"), remote=True)],
    )
    with TestClient(app) as client:
        login(client)
        _seed_binding_row(db_path, "remote")
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


def test_list_absolute_path_includes_subdir(
    files_client: TestClient, repo: Path
) -> None:
    # Regression: prior commit computed `repo_root / entry.name`, dropping
    # the subdir, which produced wrong absolute paths for any nested file
    # (e.g. operator copying `<repo>/plans/foo.md` got just `<repo>/foo.md`).
    root_resp = files_client.get("/api/bindings/demo/files")
    root_items = {i["name"]: i for i in root_resp.json()["items"]}
    assert root_items["README.md"]["absolute_path"] == str(repo / "README.md")
    assert root_items["sub"]["absolute_path"] == str(repo / "sub")

    sub_resp = files_client.get("/api/bindings/demo/files", params={"path": "sub"})
    sub_items = {i["name"]: i for i in sub_resp.json()["items"]}
    assert sub_items["nested.py"]["absolute_path"] == str(repo / "sub" / "nested.py")


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
    assert body["size"] == len("updated content\n")
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


# ──────────────────────── create ────────────────────────


def test_create_file(files_client: TestClient, repo: Path) -> None:
    resp = files_client.post("/api/bindings/demo/files", json={"path": "sub/fresh.md"})
    assert resp.status_code == 200
    assert resp.json()["path"] == "sub/fresh.md"
    assert (repo / "sub" / "fresh.md").read_text(encoding="utf-8") == ""


def test_create_existing_conflict(files_client: TestClient) -> None:
    resp = files_client.post("/api/bindings/demo/files", json={"path": "README.md"})
    assert resp.status_code == 409


def test_create_non_editable_rejected(files_client: TestClient) -> None:
    resp = files_client.post("/api/bindings/demo/files", json={"path": "new.png"})
    assert resp.status_code == 400


def test_create_traversal_rejected(files_client: TestClient) -> None:
    resp = files_client.post("/api/bindings/demo/files", json={"path": "../escape.md"})
    assert resp.status_code == 403


# ──────────────────────── delete ────────────────────────


def test_delete_file(files_client: TestClient, repo: Path) -> None:
    resp = files_client.delete(
        "/api/bindings/demo/files/content", params={"path": "README.md"}
    )
    assert resp.status_code == 200
    assert not (repo / "README.md").exists()


def test_delete_missing_404(files_client: TestClient) -> None:
    resp = files_client.delete(
        "/api/bindings/demo/files/content", params={"path": "nope.md"}
    )
    assert resp.status_code == 404


def test_delete_directory_rejected(files_client: TestClient) -> None:
    resp = files_client.delete(
        "/api/bindings/demo/files/content", params={"path": "sub"}
    )
    assert resp.status_code == 400


def test_delete_traversal_rejected(files_client: TestClient) -> None:
    resp = files_client.delete(
        "/api/bindings/demo/files/content", params={"path": "../secret"}
    )
    assert resp.status_code == 403


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


# ──────────────────────── remote bindings ────────────────────────


def test_remote_helper_compiles() -> None:
    source = base64.b64decode(main._files._REMOTE_HELPER_B64)
    compile(source, "<remote_file_browser>", "exec")


def test_remote_helper_rejects_traversal_and_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "escape").symlink_to(tmp_path)
    bootstrap = (
        "import base64,sys;exec(compile(base64.b64decode(sys.argv[1]), "
        "'<remote_file_browser>', 'exec'))"
    )
    for path in ("../secret", "escape/secret"):
        result = subprocess.run(
            [sys.executable, "-c", bootstrap, main._files._REMOTE_HELPER_B64],
            input=json.dumps(
                {
                    "action": "read",
                    "root": str(root),
                    "path": path,
                    "max_file_size": main._files.MAX_FILE_SIZE,
                    "binary_extensions": [],
                    "ignore_dirs": [],
                    "ignore_patterns": [],
                }
            ),
            text=True,
            capture_output=True,
            check=True,
        )
        assert json.loads(result.stdout) == {"ok": False, "error": "access_denied"}


def test_remote_endpoint_parity_and_transport(
    monkeypatch: pytest.MonkeyPatch, remote_files_client: TestClient
) -> None:
    responses = {
        "list": {
            "ok": True,
            "items": [
                {
                    "name": "sub",
                    "absolute_path": "/remote/repo/sub",
                    "is_directory": True,
                }
            ],
        },
        "read": {
            "ok": True,
            "content": "remote text\n",
            "size": 12,
            "modified": "2026-07-16T00:00:00+00:00",
        },
        "write": {"ok": True, "size": 8},
        "create": {"ok": True, "size": 0},
        "delete": {"ok": True},
    }
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        request = json.loads(kwargs["input"])
        calls.append((args, request))
        return subprocess.CompletedProcess(
            args, 0, json.dumps(responses[request["action"]]), ""
        )

    monkeypatch.setattr(main._files.subprocess, "run", fake_run)

    assert remote_files_client.get(
        "/api/bindings/remote/files", params={"path": "sub"}
    ).json() == {
        "items": [
            {
                "name": "sub",
                "path": "sub/sub",
                "absolute_path": "/remote/repo/sub",
                "is_directory": True,
            }
        ],
        "path": "sub",
    }
    assert (
        remote_files_client.get(
            "/api/bindings/remote/files/content", params={"path": "README.md"}
        ).json()["content"]
        == "remote text\n"
    )
    assert remote_files_client.put(
        "/api/bindings/remote/files/content",
        json={"path": "README.md", "content": "updated\n"},
    ).json() == {"message": "File saved", "path": "README.md", "size": 8}
    assert remote_files_client.post(
        "/api/bindings/remote/files", json={"path": "fresh.md"}
    ).json() == {"message": "File created", "path": "fresh.md"}
    assert remote_files_client.delete(
        "/api/bindings/remote/files/content", params={"path": "fresh.md"}
    ).json() == {"message": "File deleted", "path": "fresh.md"}

    assert [request["action"] for _, request in calls] == [
        "list",
        "read",
        "write",
        "create",
        "delete",
    ]
    for args, request in calls:
        assert args[:-1] == [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=4",
            "operator@remote.test",
        ]
        assert args[-1].startswith("python3 -c ")
        assert request["root"] == "/remote/repo"
        assert request["path"] in {"sub", "README.md", "fresh.md"}
    assert calls[2][1]["content"] == "updated\n"


@pytest.mark.parametrize(
    ("method", "url", "payload", "response", "status"),
    [
        (
            "get",
            "/api/bindings/remote/files/content?path=../secret",
            None,
            {"ok": False, "error": "access_denied"},
            403,
        ),
        (
            "get",
            "/api/bindings/remote/files/content?path=escape/secret",
            None,
            {"ok": False, "error": "access_denied"},
            403,
        ),
        (
            "get",
            "/api/bindings/remote/files/content?path=big.txt",
            None,
            {"ok": False, "error": "too_large"},
            413,
        ),
        (
            "get",
            "/api/bindings/remote/files/content?path=broken.txt",
            None,
            {"ok": False, "error": "binary"},
            400,
        ),
        (
            "get",
            "/api/bindings/remote/files/content?path=missing.txt",
            None,
            {"ok": False, "error": "missing"},
            404,
        ),
        (
            "get",
            "/api/bindings/remote/files/content?path=dir",
            None,
            {"ok": False, "error": "is_directory"},
            400,
        ),
        (
            "post",
            "/api/bindings/remote/files",
            {"path": "exists.md"},
            {"ok": False, "error": "exists"},
            409,
        ),
        (
            "put",
            "/api/bindings/remote/files/content",
            {"path": "file/child.md", "content": "x"},
            {"ok": False, "error": "invalid_parent"},
            400,
        ),
    ],
)
def test_remote_domain_errors(
    monkeypatch: pytest.MonkeyPatch,
    remote_files_client: TestClient,
    method: str,
    url: str,
    payload: dict[str, str] | None,
    response: dict[str, Any],
    status: int,
) -> None:
    calls = 0

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(args, 0, json.dumps(response), "")

    monkeypatch.setattr(main._files.subprocess, "run", fake_run)
    request = getattr(remote_files_client, method)
    response_obj = request(url) if payload is None else request(url, json=payload)
    assert response_obj.status_code == status
    assert calls == (0 if "../" in url else 1)


def test_remote_write_rejects_binary_before_ssh(
    monkeypatch: pytest.MonkeyPatch, remote_files_client: TestClient
) -> None:
    monkeypatch.setattr(
        main._files.subprocess, "run", lambda *args, **kwargs: pytest.fail("ssh called")
    )
    response = remote_files_client.put(
        "/api/bindings/remote/files/content", json={"path": "image.png", "content": "x"}
    )
    assert response.status_code == 400


@pytest.mark.parametrize("kind", ["malformed", "failure", "oserror", "timeout"])
def test_remote_transport_failures(
    monkeypatch: pytest.MonkeyPatch, remote_files_client: TestClient, kind: str
) -> None:
    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if kind == "timeout":
            raise subprocess.TimeoutExpired(args, 30)
        if kind == "oserror":
            raise OSError("ssh unavailable")
        if kind == "failure":
            return subprocess.CompletedProcess(args, 1, "", "ssh failed")
        return subprocess.CompletedProcess(args, 0, "not json", "")

    monkeypatch.setattr(main._files.subprocess, "run", fake_run)
    response = remote_files_client.get("/api/bindings/remote/files")
    assert response.status_code == (504 if kind == "timeout" else 502)


@pytest.mark.parametrize("response", [{"ok": True}, {"ok": True, "items": [{}]}])
def test_remote_malformed_success_response_is_502(
    monkeypatch: pytest.MonkeyPatch,
    remote_files_client: TestClient,
    response: dict[str, Any],
) -> None:
    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, json.dumps(response), "")

    monkeypatch.setattr(main._files.subprocess, "run", fake_run)
    assert remote_files_client.get("/api/bindings/remote/files").status_code == 502


@pytest.mark.parametrize(
    ("path", "response"),
    [
        (
            "/api/bindings/remote/files/content?path=README.md",
            {"ok": True, "content": "x", "size": True, "modified": "now"},
        ),
        (
            "/api/bindings/remote/files/content",
            {"ok": True, "size": True},
        ),
    ],
)
def test_remote_boolean_size_response_is_502(
    monkeypatch: pytest.MonkeyPatch,
    remote_files_client: TestClient,
    path: str,
    response: dict[str, Any],
) -> None:
    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, json.dumps(response), "")

    monkeypatch.setattr(main._files.subprocess, "run", fake_run)
    if path.endswith("content"):
        result = remote_files_client.put(
            path, json={"path": "README.md", "content": "x"}
        )
    else:
        result = remote_files_client.get(path)
    assert result.status_code == 502
