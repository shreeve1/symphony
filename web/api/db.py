from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

DEFAULT_DB_PATH = Path("/var/lib/symphony/podium.db")
REPO_ROOT = Path(__file__).resolve().parents[2]
FALLBACK_DB_PATH = REPO_ROOT / "podium.db"
RUN_LOG_ROOT = Path("/var/lib/symphony/runs")


def resolve_db_path() -> Path:
    override = os.environ.get("PODIUM_DB_PATH")
    if override:
        return Path(override)

    default_parent = DEFAULT_DB_PATH.parent
    if default_parent.exists() and os.access(default_parent, os.W_OK):
        return DEFAULT_DB_PATH
    return FALLBACK_DB_PATH


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
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_connection() -> Iterator[sqlite3.Connection]:
    connection = connect()
    try:
        yield connection
    finally:
        connection.close()
