from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

DEFAULT_DB_PATH = Path("/var/lib/symphony/podium.db")
REPO_ROOT = Path(__file__).resolve().parents[2]
FALLBACK_DB_PATH = REPO_ROOT / "podium.db"


def resolve_db_path() -> Path:
    override = os.environ.get("PODIUM_DB_PATH")
    if override:
        return Path(override)

    default_parent = DEFAULT_DB_PATH.parent
    if default_parent.exists() and os.access(default_parent, os.W_OK):
        return DEFAULT_DB_PATH
    return FALLBACK_DB_PATH


def resolve_run_log_root() -> Path:
    """Run logs co-locate with the active database.

    Mirrors ``resolve_db_path``'s fallback so the run-log root is never the
    unwritable ``/var/lib/symphony/runs`` default while the database itself
    resolved to the repo-root fallback. Resolved lazily so a per-process or
    per-test ``PODIUM_DB_PATH`` is honored at call time.
    """
    return resolve_db_path().parent / "runs"


def database_url() -> str:
    return f"sqlite:///{resolve_db_path()}"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or resolve_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI runs the sync get_connection dependency
    # and the sync endpoint in different anyio threadpool threads, so a
    # per-request connection is legitimately created in one thread and used in
    # another. The connection is never shared *concurrently* (one request,
    # sequential yield->endpoint->close), so disabling the guard is safe here.
    connection = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_connection() -> Iterator[sqlite3.Connection]:
    connection = connect()
    try:
        yield connection
    finally:
        connection.close()
