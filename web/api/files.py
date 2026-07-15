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

import fnmatch
import os
import sqlite3
import sys
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

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


files_router = APIRouter()


class FileWrite(BaseModel):
    path: str
    content: str


@files_router.get("/api/bindings/{name}/files")
def list_directory(
    name: str,
    path: str = Query(""),
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict:
    _require_binding_row(connection, name)
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
