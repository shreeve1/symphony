from __future__ import annotations

import asyncio
import contextlib
import inspect
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
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect

logger = logging.getLogger(__name__)

PURGE_AFTER_DAYS = 14

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
MODELS_PATH = BINDINGS_PATH.parent / "models.yml"
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
        _purge_archived_issues(connection)
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
async def login(
    request: Request, body: LoginRequest, response: Response
) -> dict[str, bool]:
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
    elif existing_revision["version_num"] != INITIAL_REVISION:
        connection.execute(
            "UPDATE alembic_version SET version_num = ?", (INITIAL_REVISION,)
        )
    connection.commit()


class IssuePatch(BaseModel):
    """Operator-editable issue fields (#013). Every field is optional; only the
    keys present in the request body are written. extra="forbid" turns unknown
    keys into validation errors, which the endpoint maps to HTTP 400."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    state: (
        Literal["todo", "in_review", "running", "blocked", "done", "archived"] | None
    ) = None
    priority: Literal["low", "med", "high", "urgent"] | None = None
    preferred_agent: str | None = None
    preferred_model: str | None = None
    preferred_skill: str | None = None
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = None
    worktree_active: bool | None = None
    approval_required: bool | None = None
    approved: bool | None = None
    scheduled_for: str | None = None
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
    approval_required: bool = False
    approved: bool = False
    scheduled_for: str | None = None
    base_branch: str | None = None


class ReplyCreate(BaseModel):
    """Operator reply payload. The single `body` field is the markdown reply
    appended as an attributed `### Operator Reply` block. extra="forbid" turns
    unknown keys into validation errors (mapped to HTTP 400); the validator
    rejects empty/whitespace-only bodies."""

    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1)

    @field_validator("body")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("body cannot be empty or whitespace-only")
        return value


# state (todo, running) returns 409.
ALLOWED_REPLY_STATES = ("in_review", "blocked", "done")
# Run states that mean a run is in flight; a reply during these races the run's
# own comments_md append, so the reply endpoint rejects them too.
ACTIVE_RUN_STATES = ("queued", "running")


# Fields whose column is conceptually NOT NULL for an operator edit: explicit
# null in the body is rejected rather than written through.
NON_NULLABLE_FIELDS = (
    "title",
    "state",
    "reasoning_effort",
    "worktree_active",
    "approval_required",
    "approved",
    "comments_md",
    "context_md",
)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    for key in ("archived", "worktree_active", "approval_required", "approved"):
        if key in result and result[key] is not None:
            result[key] = bool(result[key])
    if "binding_name" in result and "id" in result:
        binding_name = str(result["binding_name"])
        result.update(_worktree_metadata(binding_name, str(result["id"])))
        result["binding_type"] = _binding_type_for(binding_name)
    return result


def _worktree_metadata(binding_name: str, issue_id: str) -> dict[str, str]:
    try:
        from web.api.worktree import branch_name
    except ImportError:  # pragma: no cover - uvicorn --app-dir web/api path
        from worktree import branch_name  # type: ignore[no-redef]
    return {
        "worktree_path": f"worktrees/{binding_name}/{issue_id}",
        "worktree_branch": branch_name(binding_name, issue_id),
    }


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
    state: Literal["todo", "in_review", "running", "blocked", "done", "archived"]
    | None = None,
    connection: sqlite3.Connection = Depends(get_connection),
) -> list[dict[str, Any]]:
    _get_binding_or_404(connection, name)
    if state is None:
        rows = connection.execute(
            """
            SELECT
              id, binding_name, title, description, state, priority, preferred_agent,
              preferred_model, preferred_skill, reasoning_effort, worktree_active,
              approval_required, approved, scheduled_for,
              max_duration_seconds, base_branch, created_at, updated_at,
              latest_run_id, latest_verdict, latest_run_state, last_event_at
            FROM issue
            WHERE binding_name = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (name,),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT
              id, binding_name, title, description, state, priority, preferred_agent,
              preferred_model, preferred_skill, reasoning_effort, worktree_active,
              approval_required, approved, scheduled_for,
              max_duration_seconds, base_branch, created_at, updated_at,
              latest_run_id, latest_verdict, latest_run_state, last_event_at
            FROM issue
            WHERE binding_name = ? AND state = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (name, state),
        ).fetchall()
    return [_row(row) for row in rows]


@app.get("/api/inbox")
def list_inbox_issues(
    connection: sqlite3.Connection = Depends(get_connection),
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
          i.id, i.binding_name, i.title, i.description, i.state, i.priority,
          i.preferred_agent, i.preferred_model, i.preferred_skill,
          i.reasoning_effort, i.worktree_active,
          i.approval_required, i.approved, i.scheduled_for,
          i.max_duration_seconds, i.base_branch, i.created_at, i.updated_at,
          i.latest_run_id, i.latest_verdict, i.latest_run_state, i.last_event_at,
          i.inbox_dismissed_at
        FROM issue i
        INNER JOIN binding b ON b.name = i.binding_name
        WHERE i.state IN ('in_review', 'blocked')
          AND b.archived != TRUE
          AND (i.inbox_dismissed_at IS NULL
               OR i.inbox_dismissed_at < COALESCE(i.last_event_at, i.updated_at))
        ORDER BY COALESCE(i.last_event_at, i.updated_at) DESC, i.id DESC
        """
    ).fetchall()
    return [_row(row) for row in rows]


# Agents mirror the scheduler's validation set (config.py `_validate_agent`).
# Models are authored config in models.yml; preferred_model remains free text.
KNOWN_AGENTS = ["pi", "claude"]


def _validate_models(data: Any) -> list[dict[str, str]]:
    """Validate the git-tracked model catalog shared by /options and tools."""
    if not isinstance(data, dict):
        raise ValueError("models.yml must contain a mapping")
    models = data.get("models") or []
    if not isinstance(models, list):
        raise ValueError("models must be a list")

    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for index, item in enumerate(models):
        if not isinstance(item, dict):
            raise ValueError(f"models[{index}] must be a mapping")
        model_id = item.get("id")
        agent = item.get("agent")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError(f"models[{index}].id is required")
        if model_id in seen:
            raise ValueError(f"duplicate model id: {model_id}")
        if agent not in KNOWN_AGENTS:
            raise ValueError(f"models[{index}].agent must be one of {KNOWN_AGENTS}")

        entry = {"id": model_id, "agent": str(agent)}
        for key in ("provider", "label"):
            value = item.get(key)
            if value is not None:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"models[{index}].{key} must be a string")
                entry[key] = value
        result.append(entry)
        seen.add(model_id)
    return result


def _load_models(path: Path | None = None) -> list[dict[str, str]]:
    catalog_path = path or MODELS_PATH
    data = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    return _validate_models(data)


@app.get("/api/bindings/{name}/options")
def binding_issue_options(
    name: str,
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, list[Any]]:
    """Dropdown choices for the new-issue form: static agent list, model
    catalog, plus the live local branches of the binding's repo."""
    _get_binding_or_404(connection, name)
    try:
        models = _load_models()
    except (OSError, yaml.YAMLError, ValueError):
        models = []
    return {
        "agents": KNOWN_AGENTS,
        "models": models,
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
          approval_required, approved, scheduled_for, base_branch, comments_md,
          context_md, created_at, updated_at
        ) VALUES (?, ?, ?, 'todo', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', ?, ?)
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
            issue.approval_required,
            issue.approved,
            issue.scheduled_for,
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


def _binding_type_for(name: str) -> str:
    try:
        bindings = _load_bindings(BINDINGS_PATH)
    except (OSError, yaml.YAMLError):
        return "infra"
    for binding in bindings:
        if binding.get("name") == name:
            binding_type = str(binding.get("type") or "infra")
            return binding_type if binding_type in {"infra", "coding"} else "infra"
    return "infra"


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


@app.post("/api/issues/{issue_id}/compact")
async def compact_issue_context(
    issue_id: int,
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, Any]:
    _get_issue_or_404(connection, issue_id)
    return await _compact_issue_context(issue_id)


async def _compact_issue_context(issue_id: int) -> dict[str, Any]:
    compaction = import_module("context_compaction")
    from tracker_podium import CandidateIssue

    engine_main = import_module("main")
    config = vars(engine_main)["SymphonyConfig"].from_env()
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM issue WHERE id = ?", (issue_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="issue not found")
    binding_name = str(row["binding_name"] or "")
    binding = next(
        (item for item in config.bindings if item.name == binding_name), None
    )
    if binding is None:
        raise HTTPException(
            status_code=422,
            detail=f"binding {binding_name!r} is not configured for compaction",
        )
    runtime = vars(engine_main)["_build_binding_runtime"](config, binding)
    adapter = runtime.adapter
    if not getattr(adapter, "stores_context", False):
        raise HTTPException(status_code=422, detail="tracker does not store context")
    settings_fn = getattr(adapter, "context_compaction_settings", None)
    settings = {"threshold_tokens": 16_000, "keep_recent_runs": 3}
    if callable(settings_fn):
        settings_result = settings_fn(binding_name)
        if inspect.isawaitable(settings_result):
            settings_result = await settings_result
        if isinstance(settings_result, dict):
            if "threshold_tokens" in settings_result:
                settings["threshold_tokens"] = int(settings_result["threshold_tokens"])
            if "keep_recent_runs" in settings_result:
                settings["keep_recent_runs"] = int(settings_result["keep_recent_runs"])
    issue = CandidateIssue(
        id=str(row["id"]),
        identifier=str(row["id"]),
        name=str(row["title"] or ""),
        description=str(row["description"] or ""),
        labels=(),
        created_at=str(row["created_at"] or ""),
        comments_md=str(row["comments_md"] or ""),
        context_md=str(row["context_md"] or ""),
        preferred_skill=row["preferred_skill"],
        worktree_active=bool(row["worktree_active"] or False),
        base_branch=str(row["base_branch"] or ""),
        binding_name=binding_name,
    )
    compacted = await asyncio.to_thread(
        vars(compaction)["maybe_compact"],
        issue,
        binding,
        runtime.agent_adapter,
        threshold_tokens=int(settings["threshold_tokens"]),
        keep_recent_runs=int(settings["keep_recent_runs"]),
    )
    changed = compacted != issue.context_md
    if changed:
        await adapter.replace_context(str(issue_id), compacted)
    return {
        "issue_id": issue_id,
        "compacted": changed,
        "token_count": vars(compaction)["estimate_tokens"](compacted),
    }


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
    if fields.get("state") in ("in_review", "blocked") and current.get(
        "inbox_dismissed_at"
    ) is not None:
        changed["inbox_dismissed_at"] = None
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

    # Worktree merge-on-done: when state transitions to "done" and
    # worktree is active, attempt FF-merge + cleanup.
    merge_attempted = (
        "state" in changed
        and changed["state"] == "done"
        and current.get("worktree_active")
    )
    if merge_attempted:
        result = await _maybe_merge_worktree(issue_id, current, connection)

    # Archive is engine-terminal. If an issue is archived while no run is
    # active, tear down any persistent worktree immediately after publishing
    # the archived row. In-flight runs keep their worktree until completion.
    archive_attempted = "state" in changed and changed["state"] == "archived"
    if archive_attempted and result.get("latest_run_state") not in ACTIVE_RUN_STATES:
        result = await _maybe_teardown_archived_worktree(issue_id, result, connection)

    # Purge archived issues older than PURGE_AFTER_DAYS after archiving.
    # Runs inline so PATCH response is unaffected — the purge targets other
    # (older) archived issues, never the one just transitioned.
    if archive_attempted:
        _purge_archived_issues(connection)

    # Worktree toggle-off archive: toggling worktree_active from true -> false
    # while the worktree still exists appends an archive comment. If the same
    # PATCH attempted a done merge or archive teardown, that outcome wins to
    # avoid double comments or preserving a terminal archived worktree.
    if (
        not merge_attempted
        and not archive_attempted
        and "worktree_active" in changed
        and changed["worktree_active"] is False
        and current.get("worktree_active") is True
    ):
        result = await _maybe_archive_worktree(issue_id, current, connection)

    return result


@app.post("/api/issues/{issue_id}/dismiss")
async def dismiss_issue(
    issue_id: int,
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, Any]:
    stored = connection.execute(
        "SELECT * FROM issue WHERE id = ?", (issue_id,)
    ).fetchone()
    if stored is None:
        raise HTTPException(status_code=404, detail="issue not found")
    current = _row(stored)

    now = _next_updated_at(current["updated_at"])
    cursor = connection.execute(
        """
        UPDATE issue
           SET inbox_dismissed_at = ?, updated_at = ?
         WHERE id = ? AND state IN ('in_review', 'blocked')
        """,
        (now, now, issue_id),
    )
    connection.commit()

    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=409,
            detail=f"dismiss not allowed in state {current['state']}",
        )

    row = connection.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
    result = _row(row)
    await websocket_hub.publish(
        {"type": "issue.updated", "id": issue_id, "row": result}
    )
    return result


@app.post("/api/issues/{issue_id}/reply")
async def reply_to_issue(
    issue_id: int,
    body: dict[str, Any],
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, Any]:
    # No migration needed: this touches only the existing comments_md, state,
    # and updated_at columns — no new column, table, or Alembic revision.
    stored = connection.execute(
        "SELECT * FROM issue WHERE id = ?", (issue_id,)
    ).fetchone()
    if stored is None:
        raise HTTPException(status_code=404, detail="issue not found")
    current = _row(stored)

    # Hand-validate (like patch_issue): an unknown key is 400, an invalid value
    # (e.g. empty body) is 422. FastAPI would flatten both into 422.
    try:
        reply = ReplyCreate.model_validate(body)
    except ValidationError as exc:
        errors = exc.errors(include_url=False)
        # A field_validator that raises ValueError leaves the raw exception in
        # `ctx`, which is not JSON-serializable; drop ctx so the detail encodes.
        for error in errors:
            error.pop("ctx", None)
        status = 400 if any(e["type"] == "extra_forbidden" for e in errors) else 422
        raise HTTPException(status_code=status, detail=errors) from exc

    now = _next_updated_at(current["updated_at"])
    appended = f"\n\n### Operator Reply ({now})\n\n{reply.body.strip()}"

    # One atomic conditional UPDATE: append + state flip + bump, all server-side.
    # COALESCE guards a legacy NULL comments_md (NULL || text yields NULL, which
    # would silently drop the reply). The WHERE clause carries the state and
    # run-state guard so the write is gated atomically; rowcount disambiguates.
    cursor = connection.execute(
        """
        UPDATE issue
           SET comments_md = COALESCE(comments_md, '') || ?,
               state = 'todo',
               updated_at = ?
         WHERE id = ?
           AND state IN ('in_review', 'blocked', 'done')
           AND (latest_run_state IS NULL
                OR latest_run_state NOT IN ('queued', 'running'))
        """,
        (appended, now, issue_id),
    )
    connection.commit()

    if cursor.rowcount == 0:
        # Row exists (checked above), so the guard failed.
        raise HTTPException(
            status_code=409,
            detail=(
                f"reply not allowed in state {current['state']} "
                f"(run {current['latest_run_state']})"
            ),
        )

    row = connection.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
    result = _row(row)
    await websocket_hub.publish(
        {"type": "issue.updated", "id": issue_id, "row": result}
    )
    return result


async def _maybe_merge_worktree(
    issue_id: int,
    current: dict[str, Any],
    connection: sqlite3.Connection,
) -> dict[str, Any]:
    """Attempt FF-merge of worktree branch into base_branch for a done issue.

    Called after the issue has already been transitioned to ``done``. On
    failure, reverts state to ``blocked`` with an explanatory comment.
    On success, removes the worktree and branch ref.
    Returns the final issue row.
    """
    try:
        from web.api.worktree import (
            base_repo_dirty,
            branch_name,
            cleanup_worktree,
            merge_worktree,
            worktree_dir,
            worktree_exists,
        )
    except ImportError:  # pragma: no cover - uvicorn --app-dir web/api path
        from worktree import (  # type: ignore[no-redef]
            base_repo_dirty,
            branch_name,
            cleanup_worktree,
            merge_worktree,
            worktree_dir,
            worktree_exists,
        )

    binding_name = current.get("binding_name", "")
    issue_str = str(issue_id)
    base_branch = current.get("base_branch") or "main"

    repo_path = _repo_path_for_binding(binding_name)
    if not repo_path:
        return await _append_blocked_and_publish(
            connection,
            issue_id,
            current,
            f"Auto-merge halted: unknown repo_path for binding {binding_name}.",
        )

    if not await asyncio.to_thread(worktree_exists, repo_path, binding_name, issue_str):
        # No worktree to merge — nothing to do.
        return _row(
            connection.execute(
                "SELECT * FROM issue WHERE id = ?", (issue_id,)
            ).fetchone()
        )

    # Precheck: base checkout must be clean.
    if await asyncio.to_thread(base_repo_dirty, repo_path):
        msg = (
            f"Auto-merge halted: base checkout has uncommitted changes. "
            f"Branch {branch_name(binding_name, issue_str)} is unmerged. "
            f"Worktree at {worktree_dir(repo_path, binding_name, issue_str)} is intact."
        )
        return await _append_blocked_and_publish(connection, issue_id, current, msg)

    # Attempt FF-only merge.
    error = await asyncio.to_thread(
        merge_worktree, repo_path, binding_name, issue_str, base_branch
    )
    if error is not None:
        return await _append_blocked_and_publish(connection, issue_id, current, error)

    # Merge succeeded: clean up worktree + branch.
    await asyncio.to_thread(cleanup_worktree, repo_path, binding_name, issue_str)
    return _row(
        connection.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
    )


async def _maybe_teardown_archived_worktree(
    issue_id: int,
    current: dict[str, Any],
    connection: sqlite3.Connection,
) -> dict[str, Any]:
    """Remove an archived issue's idle worktree and clear worktree_active."""
    try:
        from web.api.worktree import remove_worktree, worktree_exists
    except ImportError:  # pragma: no cover - uvicorn --app-dir web/api path
        from worktree import remove_worktree, worktree_exists  # type: ignore[no-redef]

    binding_name = current.get("binding_name", "")
    issue_str = str(issue_id)
    repo_path = _repo_path_for_binding(binding_name)
    if not repo_path:
        return _row(
            connection.execute(
                "SELECT * FROM issue WHERE id = ?", (issue_id,)
            ).fetchone()
        )

    removed = False
    if await asyncio.to_thread(worktree_exists, repo_path, binding_name, issue_str):
        await asyncio.to_thread(remove_worktree, repo_path, binding_name, issue_str)
        removed = True

    if removed or current.get("worktree_active") is True:
        connection.execute(
            "UPDATE issue SET worktree_active = FALSE, updated_at = ? WHERE id = ?",
            (_next_updated_at(current.get("updated_at")), issue_id),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM issue WHERE id = ?", (issue_id,)
        ).fetchone()
        result = _row(row)
        await websocket_hub.publish(
            {"type": "issue.updated", "id": issue_id, "row": result}
        )
        return result

    return _row(
        connection.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
    )


async def _maybe_archive_worktree(
    issue_id: int,
    current: dict[str, Any],
    connection: sqlite3.Connection,
) -> dict[str, Any]:
    """Append an archive comment when worktree_active is toggled off while
    the worktree still exists. Does NOT delete the worktree — preserves
    operator intent per the issue spec."""
    try:
        from web.api.worktree import branch_name, worktree_dir, worktree_exists
    except ImportError:  # pragma: no cover - uvicorn --app-dir web/api path
        from worktree import (  # type: ignore[no-redef]
            branch_name,
            worktree_dir,
            worktree_exists,
        )

    binding_name = current.get("binding_name", "")
    issue_str = str(issue_id)
    repo_path = _repo_path_for_binding(binding_name)
    if not repo_path:
        return _row(
            connection.execute(
                "SELECT * FROM issue WHERE id = ?", (issue_id,)
            ).fetchone()
        )

    if await asyncio.to_thread(worktree_exists, repo_path, binding_name, issue_str):
        wt_path = worktree_dir(repo_path, binding_name, issue_str)
        wt_branch = branch_name(binding_name, issue_str)
        archive_note = (
            f"Worktree archived; not torn down — branch `{wt_branch}` "
            f"at `{wt_path}` persists. Toggle worktree on again or delete manually."
        )
        existing = connection.execute(
            "SELECT comments_md FROM issue WHERE id = ?", (issue_id,)
        ).fetchone()
        existing_text = str(existing["comments_md"] or "").rstrip()
        updated_comments = (
            f"{existing_text}\n\n{archive_note}".strip()
            if existing_text
            else archive_note
        )
        now = _next_updated_at(current.get("updated_at"))
        connection.execute(
            "UPDATE issue SET comments_md = ?, updated_at = ? WHERE id = ?",
            (updated_comments, now, issue_id),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM issue WHERE id = ?", (issue_id,)
        ).fetchone()
        result = _row(row)
        await websocket_hub.publish(
            {"type": "issue.updated", "id": issue_id, "row": result}
        )
        return result

    return _row(
        connection.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
    )


async def _append_blocked_and_publish(
    connection: sqlite3.Connection,
    issue_id: int,
    current: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    """Set issue state to blocked, append a merge-failure comment, publish row."""
    latest = connection.execute(
        "SELECT comments_md, updated_at FROM issue WHERE id = ?", (issue_id,)
    ).fetchone()
    existing = str(latest["comments_md"] or "").rstrip()
    updated_comments = f"{existing}\n\n{message}".strip() if existing else message
    now = _next_updated_at(latest["updated_at"])
    connection.execute(
        """
        UPDATE issue
        SET state = 'blocked', comments_md = ?, inbox_dismissed_at = NULL,
            updated_at = ?
        WHERE id = ?
        """,
        (updated_comments, now, issue_id),
    )
    connection.commit()
    row = connection.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
    result = _row(row)
    await websocket_hub.publish(
        {"type": "issue.updated", "id": issue_id, "row": result}
    )
    return result


# Overridable for tests: direct list of binding dicts bypasses disk.
_bindings_override: list[dict[str, Any]] | None = None


def _repo_path_for_binding(name: str) -> Path | None:
    """Return the repo_path for a binding name from bindings.yml, or None.

    Uses ``_bindings_override`` when set (test hook); otherwise reads
    ``BINDINGS_PATH`` from disk.
    """
    import yaml

    if _bindings_override is not None:
        raw = _bindings_override
    else:
        try:
            raw = _load_bindings(BINDINGS_PATH)
        except (OSError, yaml.YAMLError):
            return None
    for binding in raw if isinstance(raw, list) else raw.get("bindings", []):
        if binding.get("name") == name:
            repo = binding.get("repo_path")
            return Path(repo) if repo else None
    return None


def _purge_archived_issues(connection: sqlite3.Connection) -> None:
    """Hard-delete archived issues whose ``updated_at`` is > 14 days old.

    FK-safe per-issue transaction:
      1. Collect run log_path values.
      2. NULL issue.latest_run_id.
      3. DELETE FROM run WHERE issue_id = ?.
      4. DELETE FROM issue WHERE id = ?.
    After commit, best-effort unlink collected log files and defensively
    remove any persistent worktree.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=PURGE_AFTER_DAYS)).isoformat()

    eligible = connection.execute(
        "SELECT id, binding_name, worktree_active FROM issue "
        "WHERE state = 'archived' AND updated_at < ?",
        (cutoff,),
    ).fetchall()

    purged = 0
    for row in eligible:
        issue_id = int(row["id"])
        binding_name = str(row["binding_name"] or "")
        worktree_active = bool(row["worktree_active"] or False)

        # Collect run info before mutation.
        runs = connection.execute(
            "SELECT id, log_path FROM run WHERE issue_id = ?", (issue_id,)
        ).fetchall()
        log_paths = [str(r["log_path"]) for r in runs if r["log_path"]]

        try:
            connection.execute(
                "UPDATE issue SET latest_run_id = NULL WHERE id = ?", (issue_id,)
            )
            connection.execute("DELETE FROM run WHERE issue_id = ?", (issue_id,))
            connection.execute("DELETE FROM issue WHERE id = ?", (issue_id,))
            connection.commit()
        except Exception:
            connection.rollback()
            logger.exception("archive_purge_rollback issue_id=%d", issue_id)
            continue

        # Post-commit: best-effort unlink log files.
        for log_path_str in log_paths:
            try:
                Path(log_path_str).unlink(missing_ok=True)
            except Exception:
                logger.warning("archive_purge_log_unlink_failed path=%s", log_path_str)

        # Post-commit: defensive worktree removal. Check the filesystem, not
        # only worktree_active, because archive cleanup is also a drift sweep.
        try:
            from web.api.worktree import remove_worktree, worktree_exists
        except ImportError:  # pragma: no cover
            from worktree import (  # type: ignore[no-redef]
                remove_worktree,
                worktree_exists,
            )

        repo_path = _repo_path_for_binding(binding_name)
        if repo_path is not None:
            try:
                if worktree_exists(repo_path, binding_name, str(issue_id)):
                    remove_worktree(repo_path, binding_name, str(issue_id))
                elif worktree_active:
                    logger.warning(
                        "archive_purge_worktree_missing issue_id=%d binding=%s",
                        issue_id,
                        binding_name,
                    )
            except Exception:
                logger.warning(
                    "archive_purge_worktree_remove_failed issue_id=%d binding=%s",
                    issue_id,
                    binding_name,
                )

        purged += 1

    if purged > 0:
        logger.info("archive_purge purged=%d", purged)


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
