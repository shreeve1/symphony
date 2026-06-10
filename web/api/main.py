from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

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


class IssuePatch(BaseModel):
    """Operator-editable issue fields (#013). Every field is optional; only the
    keys present in the request body are written. extra="forbid" turns unknown
    keys into validation errors, which the endpoint maps to HTTP 400."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    state: Literal["todo", "in_review", "running", "blocked", "done"] | None = None
    priority: Literal["low", "med", "high", "urgent"] | None = None
    preferred_agent: str | None = None
    preferred_model: str | None = None
    preferred_skill: str | None = None
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = None
    worktree_active: bool | None = None
    max_duration_seconds: int | None = Field(default=None, ge=1)
    base_branch: str | None = None
    comments_md: str | None = None
    context_md: str | None = None


# Fields whose column is conceptually NOT NULL for an operator edit: explicit
# null in the body is rejected rather than written through.
NON_NULLABLE_FIELDS = (
    "title",
    "state",
    "reasoning_effort",
    "worktree_active",
    "comments_md",
    "context_md",
)


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


@app.patch("/api/issues/{issue_id}")
def patch_issue(
    issue_id: int,
    body: dict[str, Any],
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, Any]:
    _get_issue_or_404(connection, issue_id)

    # Validate by hand instead of typing the parameter as IssuePatch: the spec
    # distinguishes unknown fields (400) from invalid values (422), and FastAPI
    # would flatten both into 422.
    try:
        patch = IssuePatch.model_validate(body)
    except ValidationError as exc:
        errors = exc.errors(include_url=False)
        status = 400 if any(e["type"] == "extra_forbidden" for e in errors) else 422
        raise HTTPException(status_code=status, detail=errors) from exc

    fields = patch.model_dump(exclude_unset=True)
    nulled = [name for name in NON_NULLABLE_FIELDS if name in fields and fields[name] is None]
    if nulled:
        raise HTTPException(
            status_code=422, detail=f"fields cannot be null: {', '.join(nulled)}"
        )

    if fields.get("preferred_skill") is not None:
        known = connection.execute(
            "SELECT name FROM skill WHERE name = ?", (fields["preferred_skill"],)
        ).fetchone()
        if known is None:
            raise HTTPException(
                status_code=422,
                detail=f"unknown preferred_skill: {fields['preferred_skill']}",
            )

    fields["updated_at"] = _next_updated_at(connection, issue_id)
    assignments = ", ".join(f"{name} = ?" for name in fields)
    connection.execute(
        f"UPDATE issue SET {assignments} WHERE id = ?",
        (*fields.values(), issue_id),
    )
    connection.commit()

    row = connection.execute(
        "SELECT * FROM issue WHERE id = ?", (issue_id,)
    ).fetchone()
    return _row(row)


def _next_updated_at(connection: sqlite3.Connection, issue_id: int) -> str:
    """Server-side updated_at bump, strictly greater than the stored value even
    when two PATCHes land within clock resolution."""
    previous = connection.execute(
        "SELECT updated_at FROM issue WHERE id = ?", (issue_id,)
    ).fetchone()[0]
    now = datetime.now(UTC)
    if previous:
        previous_dt = datetime.fromisoformat(previous)
        if previous_dt.tzinfo is None:
            previous_dt = previous_dt.replace(tzinfo=UTC)
        if now <= previous_dt:
            now = previous_dt + timedelta(microseconds=1)
    return now.isoformat()


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
