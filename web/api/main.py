from __future__ import annotations

import asyncio
import contextlib
import logging
import sqlite3
import subprocess
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect

logger = logging.getLogger(__name__)

if __package__:
    _auth = import_module(f"{__package__}.auth")
    _db = import_module(f"{__package__}.db")
    _schema = import_module(f"{__package__}.schema")
    _seed = import_module(f"{__package__}.seed")
else:  # pragma: no cover - supports uvicorn main:app from web/api
    _auth = import_module("auth")
    _db = import_module("db")
    _schema = import_module("schema")
    _seed = import_module("seed")

COOKIE_NAME = _auth.COOKIE_NAME
SESSION_MAX_AGE_SECONDS = _auth.SESSION_MAX_AGE_SECONDS
clear_failed_attempts = _auth.clear_failed_attempts
config_from_environment = _auth.config_from_environment
rate_limited = _auth.rate_limited
record_failed_attempt = _auth.record_failed_attempt
sign_session = _auth.sign_session
verify_password = _auth.verify_password
verify_session = _auth.verify_session
resolve_run_log_root = _db.resolve_run_log_root
connect = _db.connect
get_connection = _db.get_connection
INITIAL_REVISION = _schema.INITIAL_REVISION
SCHEMA_SQL = _schema.SCHEMA_SQL
BINDINGS_PATH = _seed.BINDINGS_PATH
_load_bindings = _seed._load_bindings
seed_if_empty = _seed.seed_if_empty


class WebSocketHub:
    """Small in-process fanout hub for Podium's single-worker API."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    async def publish(self, message: dict[str, Any]) -> None:
        stale: list[asyncio.Queue[dict[str, Any]]] = []
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("websocket_queue_full; dropping subscriber")
                stale.append(queue)
        for queue in stale:
            self.unsubscribe(queue)

    async def stream(self, websocket: WebSocket) -> None:
        await websocket.accept()
        queue = self.subscribe()
        logger.info("websocket_connected")
        receive_task: asyncio.Task[str] | None = None
        send_task: asyncio.Task[dict[str, Any]] | None = None
        try:
            while True:
                receive_task = asyncio.create_task(websocket.receive_text())
                send_task = asyncio.create_task(queue.get())
                done, pending = await asyncio.wait(
                    {receive_task, send_task}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
                if receive_task in done:
                    with contextlib.suppress(WebSocketDisconnect):
                        receive_task.result()
                    break
                if send_task in done:
                    await websocket.send_json(send_task.result())
        except WebSocketDisconnect:
            pass
        finally:
            for task in (receive_task, send_task):
                if task and not task.done():
                    task.cancel()
            self.unsubscribe(queue)
            logger.info("websocket_disconnected")


websocket_hub = WebSocketHub()
_auth_config: Any | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _auth_config
    _auth_config = config_from_environment()
    connection = connect()
    try:
        ensure_schema(connection)
        seeded_run_ids = seed_if_empty(connection)
        seeded_runs = _rows_by_id(connection, "run", seeded_run_ids)
    finally:
        connection.close()
    for row in seeded_runs:
        await websocket_hub.publish(
            {"type": "run.updated", "id": row["id"], "row": row}
        )
    yield


app = FastAPI(title="Podium API", lifespan=lifespan)


class LoginRequest(BaseModel):
    password: str


def _get_auth_config() -> Any:
    global _auth_config
    if _auth_config is None:
        _auth_config = config_from_environment()
    return _auth_config


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _auth_exempt(path: str) -> bool:
    return path == "/api/health" or path.startswith("/api/auth/")


@app.middleware("http")
async def require_auth(request: Request, call_next):
    if not request.url.path.startswith("/api/") or _auth_exempt(request.url.path):
        return await call_next(request)
    config = _get_auth_config()
    if verify_session(request.cookies.get(COOKIE_NAME), config):
        return await call_next(request)
    return JSONResponse({"detail": "not authenticated"}, status_code=401)


@app.post("/api/auth/login")
async def login(request: Request, body: LoginRequest, response: Response) -> dict[str, bool]:
    config = _get_auth_config()
    ip = _client_ip(request)
    if rate_limited(ip):
        raise HTTPException(
            status_code=429,
            detail="too many failed login attempts",
            headers={"Retry-After": "60"},
        )
    if not verify_password(body.password, config):
        record_failed_attempt(ip)
        await asyncio.sleep(0.25)
        raise HTTPException(status_code=401, detail="invalid password")
    clear_failed_attempts(ip)
    response.set_cookie(
        COOKIE_NAME,
        sign_session(config),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return {"authenticated": True}


@app.post("/api/auth/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME)
    return {"authenticated": False}


@app.get("/api/auth/whoami")
def whoami(request: Request) -> dict[str, bool]:
    config = _get_auth_config()
    if not verify_session(request.cookies.get(COOKIE_NAME), config):
        raise HTTPException(status_code=401, detail="not authenticated")
    return {"authenticated": True}


@app.websocket("/api/ws")
async def websocket_events(websocket: WebSocket) -> None:
    config = _get_auth_config()
    if not verify_session(websocket.cookies.get(COOKIE_NAME), config):
        await websocket.close(code=1008)
        return
    await websocket_hub.stream(websocket)


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


class IssueCreate(BaseModel):
    """New-issue payload (#014). state is exclusively server-set ('todo'), so
    it is not a field here — extra="forbid" rejects it (and any other unknown
    key) with HTTP 400. Everything else is optional: reasoning_effort and
    worktree_active are server-defaulted but client-settable, and a null
    base_branch falls back to the binding's bindings.yml entry."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    description: str | None = None
    priority: Literal["low", "med", "high", "urgent"] | None = None
    preferred_skill: str | None = None
    preferred_agent: str | None = None
    preferred_model: str | None = None
    reasoning_effort: Literal["minimal", "low", "medium", "high"] = "high"
    worktree_active: bool = False
    base_branch: str | None = None


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


def _rows_by_id(
    connection: sqlite3.Connection, table: Literal["issue", "run"], ids: list[int]
) -> list[dict[str, Any]]:
    rows: list[sqlite3.Row] = []
    for row_id in ids:
        if table == "issue":
            row = connection.execute(
                "SELECT * FROM issue WHERE id = ?", (row_id,)
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT * FROM run WHERE id = ?", (row_id,)
            ).fetchone()
        if row is not None:
            rows.append(row)
    return [_row(row) for row in rows]


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


@app.get("/api/skills")
def list_skills(
    connection: sqlite3.Connection = Depends(get_connection),
) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT name, description, source FROM skill ORDER BY name"
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


# Agents mirror the scheduler's validation set (config.py `_validate_agent`).
# Models are a curated placeholder until a real catalog exists — the column
# stays free text server-side, so the list only shapes the UI dropdown.
KNOWN_AGENTS = ["pi", "claude"]
KNOWN_MODELS = [
    "glm-5.1:high",
    "claude-fable-5",
    "claude-opus-4-8",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
]


@app.get("/api/bindings/{name}/options")
def binding_issue_options(
    name: str,
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, list[str]]:
    """Dropdown choices for the new-issue form: static agent/model lists plus
    the live local branches of the binding's repo."""
    _get_binding_or_404(connection, name)
    return {
        "agents": KNOWN_AGENTS,
        "models": KNOWN_MODELS,
        "branches": _branches_for(name),
    }


def _branches_for(name: str) -> list[str]:
    """Local branch names from the binding's repo_path in bindings.yml. Any
    failure (missing yml, no repo_path, not a git repo) degrades to an empty
    list — the form falls back to its server-default placeholder."""
    try:
        bindings = _load_bindings(BINDINGS_PATH)
    except (OSError, yaml.YAMLError):
        return []
    repo_path = next(
        (b.get("repo_path") for b in bindings if b.get("name") == name), None
    )
    if not repo_path:
        return []
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "for-each-ref",
                "refs/heads",
                "--format=%(refname:short)",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted(line for line in result.stdout.splitlines() if line)


@app.post("/api/bindings/{name}/issues", status_code=201)
async def create_binding_issue(
    name: str,
    body: dict[str, Any],
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, Any]:
    _get_binding_or_404(connection, name)

    # Same hand-validation split as PATCH: unknown fields (e.g. a client trying
    # to pre-set `state`) are 400, invalid values are 422.
    try:
        issue = IssueCreate.model_validate(body)
    except ValidationError as exc:
        errors = exc.errors(include_url=False)
        status = 400 if any(e["type"] == "extra_forbidden" for e in errors) else 422
        raise HTTPException(status_code=status, detail=errors) from exc

    if issue.preferred_skill is not None:
        _require_known_skill(connection, issue.preferred_skill)

    now = datetime.now(UTC).isoformat()
    cursor = connection.execute(
        """
        INSERT INTO issue(
          binding_name, title, description, state, priority, preferred_agent,
          preferred_model, preferred_skill, reasoning_effort, worktree_active,
          base_branch, comments_md, context_md, created_at, updated_at
        ) VALUES (?, ?, ?, 'todo', ?, ?, ?, ?, ?, ?, ?, '', '', ?, ?)
        """,
        (
            name,
            issue.title,
            issue.description,
            issue.priority,
            issue.preferred_agent,
            issue.preferred_model,
            issue.preferred_skill,
            issue.reasoning_effort,
            issue.worktree_active,
            issue.base_branch or _base_branch_for(name),
            now,
            now,
        ),
    )
    connection.commit()
    row = connection.execute(
        "SELECT * FROM issue WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    result = _row(row)
    await websocket_hub.publish(
        {"type": "issue.created", "binding_name": name, "row": result}
    )
    return result


def _base_branch_for(name: str) -> str:
    """New-issue base_branch default comes from bindings.yml (#014 spec); the
    binding table doesn't store it. A missing or malformed file (or a binding
    present in the DB but absent from the yml) must not turn creation into a
    500 — fall back to 'main'."""
    try:
        bindings = _load_bindings(BINDINGS_PATH)
    except (OSError, yaml.YAMLError):
        return "main"
    for binding in bindings:
        if binding.get("name") == name:
            return str(binding.get("base_branch") or "main")
    return "main"


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
async def patch_issue(
    issue_id: int,
    body: dict[str, Any],
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, Any]:
    stored = connection.execute(
        "SELECT * FROM issue WHERE id = ?", (issue_id,)
    ).fetchone()
    if stored is None:
        raise HTTPException(status_code=404, detail="issue not found")
    current = _row(stored)

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
    nulled = [
        name for name in NON_NULLABLE_FIELDS if name in fields and fields[name] is None
    ]
    if nulled:
        raise HTTPException(
            status_code=422, detail=f"fields cannot be null: {', '.join(nulled)}"
        )

    if fields.get("preferred_skill") is not None:
        _require_known_skill(connection, fields["preferred_skill"])

    # No-op guard: an empty body or a patch echoing stored values must not bump
    # updated_at — the board orders by it, so a blind bump reorders cards.
    changed = {name: value for name, value in fields.items() if current[name] != value}
    if not changed:
        return current

    changed["updated_at"] = _next_updated_at(current["updated_at"])
    assignments = ", ".join(f"{name} = ?" for name in changed)
    connection.execute(
        f"UPDATE issue SET {assignments} WHERE id = ?",
        (*changed.values(), issue_id),
    )
    connection.commit()

    row = connection.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
    result = _row(row)
    await websocket_hub.publish(
        {"type": "issue.updated", "id": issue_id, "row": result}
    )
    return result


def _next_updated_at(previous: str | None) -> str:
    """Server-side updated_at bump, strictly greater than the stored value even
    when two PATCHes land within clock resolution."""
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


@app.get("/api/runs/{run_id}")
def get_run(
    run_id: int,
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, Any]:
    row = _get_run_or_404(connection, run_id)
    return _row(row)


@app.get("/api/runs/{run_id}/log")
def get_run_log(
    run_id: int,
    connection: sqlite3.Connection = Depends(get_connection),
) -> Response:
    row = _get_run_or_404(connection, run_id)
    path = Path(row["log_path"] or resolve_run_log_root() / f"{run_id}.log")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="log_not_found")
    return Response(content=_tail_bytes(path), media_type="text/plain")


def _tail_bytes(path: Path, limit: int = 1_048_576) -> bytes:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - limit))
        return handle.read()


def _require_known_skill(connection: sqlite3.Connection, skill_name: str) -> None:
    known = connection.execute(
        "SELECT name FROM skill WHERE name = ?", (skill_name,)
    ).fetchone()
    if known is None:
        raise HTTPException(
            status_code=422, detail=f"unknown preferred_skill: {skill_name}"
        )


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


def _get_run_or_404(connection: sqlite3.Connection, run_id: int) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM run WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    return row
