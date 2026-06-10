from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from importlib import import_module
from typing import Any

from fastapi import Depends, FastAPI, HTTPException

try:
    from .db import connect, get_connection
    from .schema import INITIAL_REVISION, SCHEMA_SQL
    from .seed import seed_if_empty
except ImportError:  # pragma: no cover - supports uvicorn main:app from web/api
    _db = import_module("db")
    _schema = import_module("schema")
    _seed = import_module("seed")
    connect = _db.connect
    get_connection = _db.get_connection
    INITIAL_REVISION = _schema.INITIAL_REVISION
    SCHEMA_SQL = _schema.SCHEMA_SQL
    seed_if_empty = _seed.seed_if_empty


@asynccontextmanager
async def lifespan(_app: FastAPI):
    connection = connect()
    try:
        ensure_schema(connection)
        seed_if_empty(connection)
    finally:
        connection.close()
    yield


app = FastAPI(title="Podium API", lifespan=lifespan)


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS alembic_version(version_num VARCHAR(32) NOT NULL)"
    )
    existing_revision = connection.execute(
        "SELECT version_num FROM alembic_version"
    ).fetchone()
    if existing_revision is None:
        connection.execute(
            "INSERT INTO alembic_version(version_num) VALUES (?)", (INITIAL_REVISION,)
        )
    connection.commit()


def _row(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    for key in ("archived", "worktree_active"):
        if key in result and result[key] is not None:
            result[key] = bool(result[key])
    return result


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/bindings")
def list_bindings(
    connection: sqlite3.Connection = Depends(get_connection),
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT name, display_name, color, sort_order, archived
        FROM binding
        ORDER BY sort_order, name
        """
    ).fetchall()
    return [_row(row) for row in rows]


@app.get("/api/bindings/{name}/issues")
def list_binding_issues(
    name: str,
    connection: sqlite3.Connection = Depends(get_connection),
) -> list[dict[str, Any]]:
    _get_binding_or_404(connection, name)
    rows = connection.execute(
        """
        SELECT
          id, binding_name, title, description, state, priority, preferred_agent,
          preferred_model, preferred_skill, reasoning_effort, worktree_active,
          max_duration_seconds, base_branch, created_at, updated_at,
          latest_run_id, latest_verdict, latest_run_state, last_event_at
        FROM issue
        WHERE binding_name = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (name,),
    ).fetchall()
    return [_row(row) for row in rows]


@app.get("/api/issues/{issue_id}")
def get_issue(
    issue_id: int,
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT *
        FROM issue
        WHERE id = ?
        """,
        (issue_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="issue not found")
    return _row(row)


@app.get("/api/issues/{issue_id}/runs")
def list_issue_runs(
    issue_id: int,
    connection: sqlite3.Connection = Depends(get_connection),
) -> list[dict[str, Any]]:
    _get_issue_or_404(connection, issue_id)
    rows = connection.execute(
        """
        SELECT *
        FROM run
        WHERE issue_id = ?
        ORDER BY started_at DESC, id DESC
        """,
        (issue_id,),
    ).fetchall()
    return [_row(row) for row in rows]


def _get_binding_or_404(connection: sqlite3.Connection, name: str) -> None:
    row = connection.execute(
        "SELECT name FROM binding WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="binding not found")


def _get_issue_or_404(connection: sqlite3.Connection, issue_id: int) -> None:
    row = connection.execute(
        "SELECT id FROM issue WHERE id = ?", (issue_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="issue not found")
