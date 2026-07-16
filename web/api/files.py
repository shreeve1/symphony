"""Podium file browser/editor endpoints.

Three endpoints under ``/api/bindings/{name}/files...`` let a logged-in
operator browse, read, and write text files inside a binding's ``repo_path``.
All access is sandboxed to the binding repo root with path-traversal and
symlink-escape protection (see ``_resolve_within_root``). The existing
``require_auth`` middleware in ``main.py`` already gates every ``/api/*`` path,
so these endpoints inherit session-cookie auth with no extra code.

Ported from ``cleon-ui-pi/server/files.js`` with two deliberate fixes:
  - containment uses ``os.path.commonpath`` instead of cleon's naive
    ``startsWith`` (which let ``/repo`` match ``/repo-evil``);
  - binding resolution honors live monkeypatched ``_bindings_override`` by
    resolving the already-loaded ``main`` module from ``sys.modules`` at
    request time (avoids the ``files`` <-> ``main`` import cycle).

Podium ignore policy (canonical; intentionally narrower than cleon's full
``GLOB_IGNORE_PATTERNS``): file ops are sandboxed to a binding ``repo_path``
and never to ``$HOME``, so the user/system-home ignores cleon carried
(``Library``, ``Documents``, ``etc``, ``usr`` ...) are dropped. We keep the
repo-relevant noise filters only:

  IGNORE_DIRS — directory names skipped in listings entirely.
  IGNORE_NAME_PATTERNS — per-entry glob patterns (fnmatch) skipped in listings.
"""

from __future__ import annotations

import base64
import fnmatch
import json
import os
import shlex
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from ssh_support import ssh_base_args

try:
    from .db import get_connection
except ImportError:  # pragma: no cover - supports uvicorn main:app from web/api
    get_connection = import_module("db").get_connection

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Editable file extensions (text-based files only). Ported from files.js:39.
EDITABLE_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".yaml",
    ".yml",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".py",
    ".rb",
    ".php",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".go",
    ".rs",
    ".swift",
    ".kt",
    ".kts",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".sql",
    ".graphql",
    ".gql",
    ".xml",
    ".svg",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".config",
    ".env",
    ".gitignore",
    ".dockerignore",
    ".editorconfig",
    ".vue",
    ".svelte",
    ".astro",
    ".sol",
    ".vy",
    ".lua",
    ".r",
    ".jl",
    ".dockerfile",
    # no-extension editable basenames (matched against lowercased basename)
    "dockerfile",
    "makefile",
    "rakefile",
    "gemfile",
    ".proto",
    ".thrift",
    ".graphqls",
}

# Binary file extensions to reject. Ported from files.js:108.
BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".webp",
    ".tiff",
    ".tif",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".mkv",
    ".webm",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
    ".tar",
    ".gz",
    ".rar",
    ".7z",
    ".bz2",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".app",
    ".dmg",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".eot",
    ".sqlite",
    ".db",
}

IGNORE_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".next",
    "coverage",
    "vendor",
}

IGNORE_NAME_PATTERNS = {
    ".env.local",
    ".env.*.local",
    ".DS_Store",
    "*.min.js",
    "*.min.css",
}

# Monaco language ids by extension. Monaco uses "shell" (not "bash") and
# "plaintext" for unknown types.
_LANGUAGE_MAP = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".markdown": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "css",
    ".sass": "css",
    ".less": "css",
    ".sql": "sql",
    ".go": "go",
    ".rs": "rust",
    ".toml": "toml",
}


class PathTraversal(ValueError):
    """Raised when a user path escapes the binding repo root."""


def _resolve_within_root(repo_root: Path, user_rel: str) -> Path:
    """Resolve ``user_rel`` against ``repo_root`` and enforce containment.

    Rejects absolute inputs and any input whose ``os.path.normpath`` escapes
    upward. Uses realpath + commonpath containment (fixes cleon's naive
    ``startsWith`` where ``/repo`` matched ``/repo-evil``). Empty string
    resolves to the repo root itself. Raises ``PathTraversal`` on escape.
    """
    if os.path.isabs(user_rel):
        raise PathTraversal("absolute path not allowed")

    normalized = os.path.normpath(user_rel) if user_rel else ""
    if normalized.startswith(".."):
        raise PathTraversal("path traversal attempt detected")

    root_real = os.path.realpath(repo_root)
    target_real = os.path.realpath(repo_root / user_rel)

    if target_real != root_real:
        if os.path.commonpath([target_real, root_real]) != root_real:
            raise PathTraversal("access denied: path escapes repo root")

    return Path(target_real)


def _is_editable(path: Path | str) -> bool:
    p = Path(path)
    if p.name.lower() in EDITABLE_EXTENSIONS:
        return True
    return p.suffix.lower() in EDITABLE_EXTENSIONS


def _is_binary(path: Path | str) -> bool:
    return Path(path).suffix.lower() in BINARY_EXTENSIONS


def _language_for(path: Path | str) -> str:
    p = Path(path)
    basename = p.name.lower()
    if basename == "dockerfile":
        return "dockerfile"
    if basename == "makefile":
        return "makefile"
    return _LANGUAGE_MAP.get(p.suffix.lower(), "plaintext")


def _binding_repo_root(name: str) -> Path:
    """Resolve a binding's repo root via the already-loaded main module.

    Resolved at request time from ``sys.modules`` so live monkeypatched
    ``_bindings_override`` is honored and the ``files`` <-> ``main`` import
    cycle is avoided. Raises ``HTTPException(404)`` if main is missing, the
    binding is unknown, or it has no ``repo_path``.
    """
    main_mod = sys.modules.get("web.api.main") or sys.modules.get("main")
    if main_mod is None:
        raise HTTPException(status_code=404, detail="binding not found")
    repo_path = main_mod._repo_path_for_binding(name)
    if repo_path is None:
        raise HTTPException(status_code=404, detail="binding not found")
    return Path(repo_path)


def _require_binding_row(connection: sqlite3.Connection, name: str) -> None:
    # Gate on the binding table, not just bindings.yml, matching existing
    # endpoints. Archived bindings still serve file ops: the row exists and
    # the repo remains on disk (archiving only hides from the board).
    row = connection.execute(
        "SELECT name FROM binding WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="binding not found")


def _safe_resolve(repo_root: Path, user_rel: str) -> Path:
    try:
        return _resolve_within_root(repo_root, user_rel)
    except PathTraversal as exc:
        raise HTTPException(status_code=403, detail="access denied") from exc


# The source stays out of the remote shell command: SSH receives a fixed
# bootstrap plus a base64 argument, then this helper receives only JSON stdin.
_REMOTE_HELPER = r"""
import fnmatch
import json
import os
import sys
from datetime import datetime, timezone


def fail(error):
    print(json.dumps({"ok": False, "error": error}))
    raise SystemExit


def contained(root, target):
    return target == root or os.path.commonpath([root, target]) == root


def target_for(root, path):
    if os.path.isabs(path) or os.path.normpath(path).startswith(".."):
        fail("access_denied")
    root = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root, path))
    if not contained(root, target):
        fail("access_denied")
    return root, target


def main():
    request = json.load(sys.stdin)
    root, target = target_for(request["root"], request["path"])
    action = request["action"]

    if action == "list":
        if not os.path.exists(target):
            fail("missing")
        if not os.path.isdir(target):
            fail("not_directory")
        items = []
        for entry in os.scandir(target):
            is_dir = entry.is_dir()
            if is_dir and entry.name in request["ignore_dirs"]:
                continue
            if any(fnmatch.fnmatch(entry.name, pattern) for pattern in request["ignore_patterns"]):
                continue
            items.append({"name": entry.name, "absolute_path": os.path.join(target, entry.name), "is_directory": is_dir})
        items.sort(key=lambda item: (not item["is_directory"], item["name"].lower()))
        print(json.dumps({"ok": True, "items": items}))
        return

    if action == "read":
        if not os.path.exists(target):
            fail("missing")
        if os.path.isdir(target):
            fail("is_directory")
        stat = os.stat(target)
        if stat.st_size > request["max_file_size"]:
            fail("too_large")
        if os.path.splitext(target)[1].lower() in request["binary_extensions"]:
            fail("binary")
        try:
            with open(target, encoding="utf-8") as handle:
                content = handle.read()
        except UnicodeDecodeError:
            fail("binary")
        print(json.dumps({"ok": True, "content": content, "size": stat.st_size, "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()}))
        return

    if action in {"write", "create"}:
        parent = os.path.realpath(os.path.dirname(target))
        if not contained(root, parent):
            fail("access_denied")
        if action == "create" and os.path.exists(target):
            fail("exists")
        try:
            os.makedirs(parent, exist_ok=True)
        except (FileExistsError, NotADirectoryError):
            fail("invalid_parent")
        parent = os.path.realpath(parent)
        target = os.path.realpath(os.path.join(parent, os.path.basename(target)))
        if not contained(root, parent) or not contained(root, target):
            fail("access_denied")
        if os.path.isdir(target):
            fail("is_directory")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(request.get("content", ""))
        print(json.dumps({"ok": True, "size": len(request.get("content", "").encode("utf-8"))}))
        return

    if action == "delete":
        if not os.path.exists(target):
            fail("missing")
        if os.path.isdir(target):
            fail("is_directory")
        os.unlink(target)
        print(json.dumps({"ok": True}))
        return

    fail("invalid_action")


main()
"""
_REMOTE_HELPER_B64 = base64.b64encode(_REMOTE_HELPER.encode()).decode()
_REMOTE_BOOTSTRAP = (
    "import base64,sys;exec(compile(base64.b64decode(sys.argv[1]), "
    "'<remote_file_browser>', 'exec'))"
)
_REMOTE_COMMAND = (
    f"python3 -c {shlex.quote(_REMOTE_BOOTSTRAP)} {shlex.quote(_REMOTE_HELPER_B64)}"
)


def _remote_file_operation(
    name: str, action: str, path: str, content: str | None = None
) -> dict:
    if os.path.isabs(path) or os.path.normpath(path).startswith(".."):
        raise HTTPException(status_code=403, detail="access denied")
    main_mod = sys.modules.get("web.api.main") or sys.modules.get("main")
    if main_mod is None:
        raise HTTPException(status_code=404, detail="binding not found")
    remote = main_mod._remote_for_binding(name)
    repo_root = main_mod._repo_path_for_binding(name)
    if remote is None or repo_root is None:
        raise HTTPException(status_code=502, detail="remote binding unavailable")

    request = {
        "action": action,
        "root": str(repo_root),
        "path": path,
        "max_file_size": MAX_FILE_SIZE,
        "binary_extensions": sorted(BINARY_EXTENSIONS),
        "ignore_dirs": sorted(IGNORE_DIRS),
        "ignore_patterns": sorted(IGNORE_NAME_PATTERNS),
    }
    if content is not None:
        request["content"] = content
    try:
        result = subprocess.run(
            ssh_base_args(remote) + [_REMOTE_COMMAND],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=504, detail="remote file operation timed out"
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=502, detail="remote file operation failed"
        ) from exc
    if result.returncode:
        raise HTTPException(status_code=502, detail="remote file operation failed")
    try:
        response = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502, detail="invalid remote file response"
        ) from exc
    if not isinstance(response, dict) or not isinstance(response.get("ok"), bool):
        raise HTTPException(status_code=502, detail="invalid remote file response")
    if response["ok"]:
        expected_fields = {
            "list": {"items": list},
            "read": {"content": str, "size": int, "modified": str},
            "write": {"size": int},
            "create": {},
            "delete": {},
        }[action]
        if not all(
            type(response.get(field)) is int
            if kind is int
            else isinstance(response.get(field), kind)
            for field, kind in expected_fields.items()
        ):
            raise HTTPException(status_code=502, detail="invalid remote file response")
        if action == "list" and not all(
            isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("absolute_path"), str)
            and isinstance(item.get("is_directory"), bool)
            for item in response["items"]
        ):
            raise HTTPException(status_code=502, detail="invalid remote file response")
        return response

    error = response.get("error")
    details = {
        "access_denied": (403, "access denied"),
        "too_large": (413, "file too large"),
        "binary": (400, "binary file - cannot edit"),
        "exists": (409, "file already exists"),
        "invalid_parent": (400, "invalid parent path"),
    }
    if error in details:
        status, detail = details[error]
    elif error == "missing":
        status, detail = (
            404,
            ("directory not found" if action == "list" else "file not found"),
        )
    elif error == "not_directory":
        status, detail = 400, "not a directory"
    elif error == "is_directory":
        status, detail = (
            400,
            {
                "read": "cannot read directory",
                "delete": "cannot delete directory",
            }.get(action, "cannot write directory"),
        )
    else:
        raise HTTPException(status_code=502, detail="invalid remote file response")
    raise HTTPException(status_code=status, detail=detail)


def _is_remote_binding(name: str) -> bool:
    main_mod = sys.modules.get("web.api.main") or sys.modules.get("main")
    return bool(main_mod and main_mod._is_remote_binding(name))


files_router = APIRouter()


class FileWrite(BaseModel):
    path: str
    content: str


class FileCreate(BaseModel):
    path: str


@files_router.get("/api/bindings/{name}/files")
def list_directory(
    name: str,
    path: str = Query(""),
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict:
    _require_binding_row(connection, name)
    if _is_remote_binding(name):
        result = _remote_file_operation(name, "list", path)
        return {
            "items": [
                {**item, "path": f"{path}/{item['name']}" if path else item["name"]}
                for item in result["items"]
            ],
            "path": path,
        }

    repo_root = _binding_repo_root(name)
    target = _safe_resolve(repo_root, path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="directory not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="not a directory")

    items = []
    for entry in os.scandir(target):
        is_dir = entry.is_dir()
        if is_dir and entry.name in IGNORE_DIRS:
            continue
        if any(fnmatch.fnmatch(entry.name, pat) for pat in IGNORE_NAME_PATTERNS):
            continue
        items.append(
            {
                "name": entry.name,
                "path": f"{path}/{entry.name}" if path else entry.name,
                "absolute_path": str(target / entry.name),
                "is_directory": is_dir,
            }
        )

    items.sort(key=lambda i: (not i["is_directory"], i["name"].lower()))
    return {"items": items, "path": path}


@files_router.get("/api/bindings/{name}/files/content")
def read_file(
    name: str,
    path: str = Query(...),
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict:
    _require_binding_row(connection, name)
    if _is_remote_binding(name):
        result = _remote_file_operation(name, "read", path)
        return {
            "path": path,
            "content": result["content"],
            "size": result["size"],
            "modified": result["modified"],
            "editable": _is_editable(path),
            "language": _language_for(path),
        }

    repo_root = _binding_repo_root(name)
    target = _safe_resolve(repo_root, path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="cannot read directory")

    stat = target.stat()
    if stat.st_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="file too large")
    if _is_binary(target):
        raise HTTPException(status_code=400, detail="binary file - cannot edit")

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        # Binary check above is extension-only; non-text bytes in an editable
        # or extensionless file would otherwise 500 here.
        raise HTTPException(
            status_code=400, detail="binary file - cannot edit"
        ) from exc
    modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()

    return {
        "path": path,
        "content": content,
        "size": stat.st_size,
        "modified": modified,
        "editable": _is_editable(target),
        "language": _language_for(target),
    }


@files_router.put("/api/bindings/{name}/files/content")
def write_file(
    name: str,
    body: FileWrite,
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict:
    _require_binding_row(connection, name)
    if _is_remote_binding(name):
        if not _is_editable(body.path):
            raise HTTPException(status_code=400, detail="file type is not editable")
        encoded = body.content.encode("utf-8")
        if len(encoded) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="file too large")
        result = _remote_file_operation(name, "write", body.path, body.content)
        return {"message": "File saved", "path": body.path, "size": result["size"]}

    repo_root = _binding_repo_root(name)
    target = _safe_resolve(repo_root, body.path)

    if not _is_editable(target):
        raise HTTPException(status_code=400, detail="file type is not editable")

    encoded = body.content.encode("utf-8")
    if len(encoded) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="file too large")

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except (FileExistsError, NotADirectoryError) as exc:
        # A path component (e.g. README.md in "README.md/new.txt") is an
        # existing file, not a directory.
        raise HTTPException(status_code=400, detail="invalid parent path") from exc
    target.write_text(body.content, encoding="utf-8")

    return {"message": "File saved", "path": body.path, "size": len(encoded)}


@files_router.post("/api/bindings/{name}/files")
def create_file(
    name: str,
    body: FileCreate,
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict:
    _require_binding_row(connection, name)
    if _is_remote_binding(name):
        if not _is_editable(body.path):
            raise HTTPException(status_code=400, detail="file type is not editable")
        _remote_file_operation(name, "create", body.path)
        return {"message": "File created", "path": body.path}

    repo_root = _binding_repo_root(name)
    target = _safe_resolve(repo_root, body.path)

    if not _is_editable(target):
        raise HTTPException(status_code=400, detail="file type is not editable")
    if target.exists():
        raise HTTPException(status_code=409, detail="file already exists")

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except (FileExistsError, NotADirectoryError) as exc:
        # A path component is an existing file, not a directory.
        raise HTTPException(status_code=400, detail="invalid parent path") from exc
    target.write_text("", encoding="utf-8")

    return {"message": "File created", "path": body.path}


@files_router.delete("/api/bindings/{name}/files/content")
def delete_file(
    name: str,
    path: str = Query(...),
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict:
    _require_binding_row(connection, name)
    if _is_remote_binding(name):
        _remote_file_operation(name, "delete", path)
        return {"message": "File deleted", "path": path}

    repo_root = _binding_repo_root(name)
    target = _safe_resolve(repo_root, path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="cannot delete directory")
    target.unlink()

    return {"message": "File deleted", "path": path}
