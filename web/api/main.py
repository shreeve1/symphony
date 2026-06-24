from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sqlite3
import subprocess
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)
from starlette.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect

try:
    from proc_runtime import tail_spool_path
    from session_continuity import derive_session_id, session_file_path
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from proc_runtime import tail_spool_path  # type: ignore[no-redef]
    from session_continuity import derive_session_id, session_file_path  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

PURGE_AFTER_DAYS = 14

if __package__:
    _auth = import_module(f"{__package__}.auth")
    _db = import_module(f"{__package__}.db")
    _schema = import_module(f"{__package__}.schema")
    _seed = import_module(f"{__package__}.seed")
    _steer_queue = import_module(f"{__package__}.steer_queue")
    _wake_signal = import_module(f"{__package__}.wake_signal")
    _files = import_module(f"{__package__}.files")
else:  # pragma: no cover - supports uvicorn main:app from web/api
    _auth = import_module("auth")
    _db = import_module("db")
    _schema = import_module("schema")
    _seed = import_module("seed")
    _steer_queue = import_module("steer_queue")
    _wake_signal = import_module("wake_signal")
    _files = import_module("files")

COOKIE_NAME = _auth.COOKIE_NAME
SESSION_MAX_AGE_SECONDS = _auth.SESSION_MAX_AGE_SECONDS
clear_failed_attempts = _auth.clear_failed_attempts
config_from_environment = _auth.config_from_environment
rate_limited = _auth.rate_limited
record_failed_attempt = _auth.record_failed_attempt
sign_session = _auth.sign_session
verify_password = _auth.verify_password
verify_session = _auth.verify_session
verify_bearer_token = _auth.verify_bearer_token
resolve_run_log_root = _db.resolve_run_log_root
connect = _db.connect
get_connection = _db.get_connection
INITIAL_REVISION = _schema.INITIAL_REVISION
SCHEMA_SQL = _schema.SCHEMA_SQL
BINDINGS_PATH = _seed.BINDINGS_PATH
MODELS_PATH = (
    Path(os.environ["PODIUM_MODELS_PATH"])
    if os.environ.get("PODIUM_MODELS_PATH")
    # Default to the stable repo root, NOT BINDINGS_PATH.parent: BINDINGS_PATH is
    # overridable via PODIUM_BINDINGS_PATH (e2e isolation), and deriving from it
    # would point the model catalog at a nonexistent test-results/models.yml.
    else (_seed.REPO_ROOT / "models.yml")
)
_load_bindings = _seed._load_bindings
seed_if_empty = _seed.seed_if_empty
touch_wake_sentinel = _wake_signal.touch_wake_sentinel
write_steer_record = _steer_queue.write_steer_record


try:
    _model_catalog = import_module("model_catalog")
    _schedule = import_module("schedule")
except ModuleNotFoundError:  # pragma: no cover - uvicorn main:app from web/api
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    _model_catalog = import_module("model_catalog")
    _schedule = import_module("schedule")

format_cancellation_comment = _schedule.format_cancellation_comment
format_schedule_comment = _schedule.format_schedule_comment
next_maintenance_window = _schedule.next_maintenance_window
parse_schedule_comment = _schedule.parse_schedule_comment
ScheduleParseError = _schedule.ScheduleParseError


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


class _SessionTailer:
    """Tails session files of running issues and emits run.tail WS events."""

    _POLL_INTERVAL_S = 2.0

    def __init__(self) -> None:
        # issue_id -> {path, cursor, inode}
        self._state: dict[int, dict[str, Any]] = {}
        self._stop: asyncio.Event = asyncio.Event()

    async def run_loop(self) -> None:
        """Poll loop that runs until stop is set."""
        while not self._stop.is_set():
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self._POLL_INTERVAL_S)
            try:
                await self._poll_running()
            except Exception:
                logger.exception("session_tail_poll_error")

    def shutdown(self) -> None:
        self._stop.set()

    async def _poll_running(self) -> None:
        """Query DB for running issues, tail their session files, emit events."""
        try:
            connection = connect()
        except Exception:
            return
        try:
            rows = connection.execute(
                """
                SELECT i.id, i.binding_name, r.agent, r.id AS run_id
                FROM issue i
                INNER JOIN run r ON r.id = i.latest_run_id
                WHERE i.latest_run_state = 'running'
                """
            ).fetchall()
        finally:
            connection.close()

        current_ids: set[int] = set()
        for row in rows:
            issue_id = int(row["id"])
            binding_name = str(row["binding_name"] or "")
            agent = str(row["agent"] or "").strip().lower()
            if not agent or agent not in ("pi", "claude"):
                continue
            current_ids.add(issue_id)

            if _is_remote_binding(binding_name):
                # Remote agents write their transcript on the remote host; the
                # scheduler spools the RPC stream to a local file instead so we
                # can tail it without reaching the remote FS (ADR-0019).
                run_id = row["run_id"]
                if run_id is None:
                    continue
                s_path = tail_spool_path(str(run_id))
            else:
                repo_path = _repo_path_for_binding(binding_name)
                if not repo_path:
                    continue

                session_id = derive_session_id(issue_id)
                try:
                    s_path = session_file_path(agent, repo_path, session_id)
                except (ValueError, OSError):
                    continue

            lines = self._read_new_lines(issue_id, s_path)
            if lines:
                await websocket_hub.publish(
                    {
                        "type": "run.tail",
                        "issue_id": issue_id,
                        "lines": lines,
                    }
                )

        # Cleanup stale tracked issues no longer running
        for issue_id in list(self._state):
            if issue_id not in current_ids:
                del self._state[issue_id]

    def _read_new_lines(self, issue_id: int, path: Path) -> list[str]:
        """Read new JSONL lines appended since last poll. On first encounter,
        reads the entire existing content so the operator catches up."""
        try:
            stat_result = path.stat()
        except OSError:
            # File does not exist yet — first poll, fine
            self._state.setdefault(issue_id, {"path": path, "cursor": 0, "inode": 0})
            return []

        current_inode = stat_result.st_ino
        current_size = stat_result.st_size
        tracked = self._state.get(issue_id)

        if tracked is None or tracked["inode"] != current_inode:
            # First detection or file rotated: read all existing content
            self._state[issue_id] = {
                "path": path,
                "cursor": current_size,
                "inode": current_inode,
            }
            # On first detection, emit existing content so the operator sees
            # the full session so far
            if current_size == 0:
                return []
            try:
                return _read_jsonl_lines(path, 0, current_size)
            except OSError:
                return []

        if current_size <= tracked["cursor"]:
            return []

        try:
            lines = _read_jsonl_lines(path, tracked["cursor"], current_size)
        except OSError:
            return []

        tracked["cursor"] = current_size
        return lines


def _read_jsonl_lines(path: Path, start: int, end: int) -> list[str]:
    """Read and split the byte range [start, end) into non-empty lines."""
    with path.open("rb") as f:
        f.seek(start)
        raw = f.read(end - start)
    return [line for line in raw.decode("utf-8", errors="replace").split("\n") if line]


_session_tailer = _SessionTailer()
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
    tail_task = asyncio.create_task(_session_tailer.run_loop())
    try:
        yield
    finally:
        _session_tailer.shutdown()
        tail_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tail_task


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
    # Service-to-service callers (e.g. the Temporal patrol worker) authenticate
    # with a Bearer token instead of the browser session cookie.
    if verify_bearer_token(request.headers.get("authorization"), config):
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


def _expected_columns() -> dict[str, set[str]]:
    """Table -> column-name set from the runtime SCHEMA_SQL."""
    with contextlib.closing(sqlite3.connect(":memory:")) as reference:
        reference.executescript(SCHEMA_SQL)
        tables = [
            row[0]
            for row in reference.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
                " AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
            )
        ]
        return {
            table: {row[1] for row in reference.execute(f"PRAGMA table_info({table})")}
            for table in tables
        }


def _schema_drift(connection: sqlite3.Connection) -> tuple[list[str], list[str]]:
    """Return (missing, extra) `table.column` entries vs the runtime schema."""
    missing: list[str] = []
    extra: list[str] = []
    for table, expected in _expected_columns().items():
        live = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if not live:
            missing.append(f"{table} (entire table)")
            continue
        missing.extend(f"{table}.{name}" for name in sorted(expected - live))
        extra.extend(f"{table}.{name}" for name in sorted(live - expected))
    return missing, extra


def ensure_schema(connection: sqlite3.Connection) -> None:
    """Create a fresh Podium schema, or verify an existing one.

    Fresh databases are built from SCHEMA_SQL and stamped at INITIAL_REVISION
    (they already have the head schema). Existing databases are NEVER
    re-stamped: a revision that disagrees with the code means pending
    migrations, and stamping over it is how the 2026-06-12 stamp-vs-run drift
    happened (alembic_version said 0005 while inbox_dismissed_at did not
    exist). Instead, missing columns fail startup loudly and extra columns
    (a pending column-drop migration) only warn.
    """
    existing_revision = None
    has_version_table = connection.execute(
        "SELECT name FROM sqlite_schema WHERE type = 'table'"
        " AND name = 'alembic_version'"
    ).fetchone()
    if has_version_table:
        existing_revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()

    if existing_revision is None:
        connection.executescript(SCHEMA_SQL)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS alembic_version(version_num VARCHAR(32) NOT NULL)"
        )
        connection.execute(
            "INSERT INTO alembic_version(version_num) VALUES (?)", (INITIAL_REVISION,)
        )
        connection.commit()
        return

    revision = str(existing_revision["version_num"])
    if revision != INITIAL_REVISION:
        logger.warning(
            "podium_schema_revision_mismatch db=%s code=%s; refusing to stamp"
            " — run `uv run alembic upgrade head`",
            revision,
            INITIAL_REVISION,
        )
    missing, extra = _schema_drift(connection)
    if missing:
        raise RuntimeError(
            f"Podium DB schema drift: missing columns {missing}"
            f" (alembic_version={revision}, code expects {INITIAL_REVISION});"
            " run `uv run alembic upgrade head` before starting the API"
        )
    if extra:
        logger.warning(
            "podium_schema_extra_columns columns=%s — pending drop migration?"
            " run `uv run alembic upgrade head`",
            extra,
        )


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
    reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None
    ) = None
    worktree_active: bool | None = None
    approval_required: bool | None = None
    approved: bool | None = None
    auto_land: bool | None = None
    scheduled_for: str | None = None
    base_branch: str | None = None
    comments_md: str | None = None
    context_md: str | None = None
    external_id: str | None = None
    blocked_by: list[int] | None = None
    locks: list[str] | None = None


class ScheduleRequest(BaseModel):
    """Manual scheduling payload. `next_window` is resolved server-side; explicit
    datetimes must be ISO 8601 with an offset, matching schedule.py's grammar."""

    model_config = ConfigDict(extra="forbid")

    not_before: str
    reason: str | None = None


class UnscheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None


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
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] = (
        "high"
    )
    worktree_active: bool = False
    approval_required: bool = False
    approved: bool = False
    auto_land: bool = False
    scheduled_for: str | None = None
    schedule: ScheduleRequest | None = None
    base_branch: str | None = None
    external_id: str | None = None
    blocked_by: list[int] | None = None
    locks: list[str] | None = None


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


class SteerCreate(BaseModel):
    """Live agent steering payload.

    `action=steer` requires a non-empty body. `action=abort` may omit body and
    forwards an abort command to the active run.
    """

    model_config = ConfigDict(extra="forbid")

    action: Literal["steer", "abort"] = "steer"
    body: str | None = None


# state (todo, running) returns 409.
ALLOWED_REPLY_STATES = ("in_review", "blocked", "done")
# Run states that mean a run is in flight; a reply during these races the run's
# own comments_md append, so the reply endpoint rejects them too.
ACTIVE_RUN_STATES = ("queued", "running")

# Worktree done-time commit re-dispatch (ADR-0014). When an Issue with an
# active worktree is marked `done` but the worktree is dirty (uncommitted
# work), Symphony re-dispatches the agent to commit its own work rather than
# silently force-removing the worktree. Capped to avoid an infinite loop when
# the agent repeatedly fails to commit; over the cap, fall back to `blocked`.
MAX_COMMIT_REDISPATCH = 2
# Substring used both as the synthetic operator-reply header and as the marker
# counted to enforce MAX_COMMIT_REDISPATCH. Must keep the `### Operator Reply (`
# shape so prompt_renderer's operator-reply regex surfaces it on resume.
COMMIT_REDISPATCH_REPLY_PREFIX = "### Operator Reply (Symphony auto-commit"


# Fields whose column is conceptually NOT NULL for an operator edit: explicit
# null in the body is rejected rather than written through.
NON_NULLABLE_FIELDS = (
    "title",
    "state",
    "reasoning_effort",
    "worktree_active",
    "approval_required",
    "approved",
    "auto_land",
    "comments_md",
    "context_md",
)


def _json_list(value: Any, item_type: type) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        parsed = value
    else:
        try:
            parsed = json.loads(str(value))
        except (TypeError, ValueError):
            return []
    if not isinstance(parsed, list):
        return []
    items: list[Any] = []
    for item in parsed:
        try:
            items.append(item_type(item))
        except (TypeError, ValueError):
            continue
    return items


def _blocked_by_has_cycle(
    connection: sqlite3.Connection, issue_id: int, blocked_by: list[int]
) -> bool:
    edges = {
        int(row["id"]): _json_list(row["blocked_by"], int)
        for row in connection.execute("SELECT id, blocked_by FROM issue").fetchall()
    }
    edges[issue_id] = blocked_by

    seen: set[int] = set()

    def visit(node: int) -> bool:
        if node == issue_id:
            return True
        if node in seen:
            return False
        seen.add(node)
        return any(visit(parent) for parent in edges.get(node, []))

    return any(visit(parent) for parent in blocked_by)


DONE_DEPENDENCY_STATES = {"done", "archived"}


def _decorate_issue_gates(
    connection: sqlite3.Connection, issues: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    blocker_states = {
        int(row["id"]): str(row["state"])
        for row in connection.execute("SELECT id, state FROM issue").fetchall()
    }

    binding_names = {
        str(issue["binding_name"]) for issue in issues if "binding_name" in issue
    }
    active_locks: dict[str, set[str]] = {name: set() for name in binding_names}
    rows = connection.execute(
        """
        SELECT binding_name, locks
        FROM issue
        WHERE state = 'running' OR latest_run_state IN ('queued', 'running')
        """
    ).fetchall()
    for row in rows:
        binding_name = str(row["binding_name"])
        if binding_name in binding_names:
            active_locks.setdefault(binding_name, set()).update(
                _json_list(row["locks"], str)
            )

    for issue in issues:
        unsatisfied = [
            blocker
            for blocker in issue.get("blocked_by", [])
            if blocker_states.get(int(blocker)) not in (None, *DONE_DEPENDENCY_STATES)
        ]
        issue["unsatisfied_blocked_by"] = unsatisfied
        issue["dependencies_satisfied"] = not unsatisfied
        locks = set(issue.get("locks", []))
        issue["lock_conflicts"] = sorted(
            locks & active_locks.get(str(issue.get("binding_name")), set())
        )
    return issues


def _row(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    for key in (
        "archived",
        "worktree_active",
        "approval_required",
        "approved",
        "auto_land",
    ):
        if key in result and result[key] is not None:
            result[key] = bool(result[key])
    if "blocked_by" in result:
        result["blocked_by"] = _json_list(result["blocked_by"], int)
    if "locks" in result:
        result["locks"] = _json_list(result["locks"], str)
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
    result = [_row(row) for row in rows]
    for binding in result:
        name = str(binding["name"])
        binding["binding_type"] = _binding_type_for(name)
        binding["pi_mode"] = _binding_pi_mode_for(name)
        binding["claude_persist"] = _binding_claude_persist_for(name)
        binding["approval_enabled"] = _binding_approval_enabled_for(name)
        binding["is_remote"] = _is_remote_binding(name)
        repo_path = _repo_path_for_binding(name)
        binding["repo_name"] = repo_path.name if repo_path is not None else None
    return result


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
    external_id: str | None = None,
    connection: sqlite3.Connection = Depends(get_connection),
) -> list[dict[str, Any]]:
    _get_binding_or_404(connection, name)
    # external_id powers PodiumAdapter.find_by_external_id (ADR-0015); it ANDs
    # cleanly with the existing optional state filter.
    clauses = ["binding_name = ?"]
    params: list[Any] = [name]
    if state is not None:
        clauses.append("state = ?")
        params.append(state)
    if external_id is not None:
        clauses.append("external_id = ?")
        params.append(external_id)
    rows = connection.execute(
        f"""
        SELECT
          id, binding_name, title, description, state, priority, preferred_agent,
          preferred_model, preferred_skill, reasoning_effort, worktree_active,
          approval_required, approved, auto_land, scheduled_for,
          base_branch, created_at, updated_at,
          latest_run_id, latest_verdict, latest_run_state, last_event_at,
          external_id, blocked_by, locks
        FROM issue
        WHERE {" AND ".join(clauses)}
        ORDER BY updated_at DESC, id DESC
        """,
        tuple(params),
    ).fetchall()
    return _decorate_issue_gates(connection, [_row(row) for row in rows])


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
          i.approval_required, i.approved, i.auto_land, i.scheduled_for,
          i.base_branch, i.created_at, i.updated_at,
          i.latest_run_id, i.latest_verdict, i.latest_run_state, i.last_event_at,
          i.inbox_dismissed_at, i.blocked_by, i.locks
        FROM issue i
        INNER JOIN binding b ON b.name = i.binding_name
        WHERE i.state IN ('in_review', 'blocked')
          AND b.archived != TRUE
          AND (i.inbox_dismissed_at IS NULL
               OR i.inbox_dismissed_at < COALESCE(i.last_event_at, i.updated_at))
        ORDER BY COALESCE(i.last_event_at, i.updated_at) DESC, i.id DESC
        """
    ).fetchall()
    return _decorate_issue_gates(connection, [_row(row) for row in rows])


# Agents mirror the scheduler's validation set (config.py `_validate_agent`).
# Models are authored config in models.yml; the scheduler resolves
# preferred_model against the catalog at dispatch and fails loudly on
# unknown ids, so the dropdown is the contract, not a hint.
KNOWN_AGENTS = _model_catalog.KNOWN_AGENTS

# Kept as module-level names: the symphony-models skill and tests import
# _load_models/_validate_models from web.api.main.
_validate_models = _model_catalog.validate_models


def _load_models(path: Path | None = None) -> list[dict[str, Any]]:
    return _model_catalog.load_models(path or MODELS_PATH)


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

    if issue.schedule is not None and _binding_type_for(name) != "infra":
        raise HTTPException(status_code=400, detail="scheduling is infra-only")

    # Remote bindings (ADR-0012) defer worktrees: the agent runs directly in the
    # remote repo_path over SSH, so worktree_active is forced False at the source.
    if issue.worktree_active and _is_remote_binding(name):
        issue.worktree_active = False

    now_dt = datetime.now(UTC)
    now = now_dt.isoformat()
    comments_md = ""
    scheduled_for = issue.scheduled_for
    if issue.schedule is not None:
        not_before, reason = _resolve_schedule_request(issue.schedule, now_dt)
        comments_md = format_schedule_comment(not_before=not_before, reason=reason)
        scheduled_for = now
    blocked_by = issue.blocked_by or []
    locks = issue.locks or []
    try:
        cursor = connection.execute(
            """
            INSERT INTO issue(
              binding_name, title, description, state, priority, preferred_agent,
              preferred_model, preferred_skill, reasoning_effort, worktree_active,
              approval_required, approved, auto_land, scheduled_for, base_branch, comments_md,
              context_md, external_id, blocked_by, locks, created_at, updated_at
            ) VALUES (?, ?, ?, 'todo', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?)
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
                issue.auto_land,
                scheduled_for,
                issue.base_branch or _base_branch_for(name),
                comments_md,
                issue.external_id,
                json.dumps(blocked_by),
                json.dumps(locks),
                now,
                now,
            ),
        )
        issue_id = cursor.lastrowid
        if issue_id is None:
            raise RuntimeError("insert did not return an issue id")
        if _blocked_by_has_cycle(connection, issue_id, blocked_by):
            connection.rollback()
            raise HTTPException(status_code=400, detail="blocked_by cycle detected")
    except sqlite3.IntegrityError as exc:
        # Global UNIQUE(external_id) (ADR-0015): a duplicate external_id is the
        # adapter's dedup signal, surfaced as a conflict so the caller can fall
        # back to find_by_external_id + update rather than create.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    connection.commit()
    row = connection.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
    result = _decorate_issue_gates(connection, [_row(row)])[0]
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


def _resolve_schedule_request(
    schedule: ScheduleRequest,
    now: datetime,
    *,
    default_reason: str = "operator scheduled via Podium",
) -> tuple[datetime, str]:
    reason = schedule.reason if schedule.reason is not None else default_reason
    raw_not_before = schedule.not_before.strip()
    if raw_not_before == "next_window":
        not_before, _ = next_maintenance_window(now)
    else:
        try:
            event = parse_schedule_comment(
                f'Symphony-Schedule: not_before={raw_not_before} reason="operator"',
                now=now,
            )
        except ScheduleParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        not_before = event.not_before
        if not_before is None:
            raise HTTPException(status_code=422, detail="not_before is required")
        if not_before < now:
            raise HTTPException(status_code=422, detail="not_before is in the past")
    try:
        format_schedule_comment(not_before=not_before, reason=reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return not_before, reason


def _validate_schedule_payload(body: dict[str, Any]) -> ScheduleRequest:
    try:
        return ScheduleRequest.model_validate(body)
    except ValidationError as exc:
        errors = exc.errors(include_url=False)
        status = 400 if any(e["type"] == "extra_forbidden" for e in errors) else 422
        raise HTTPException(status_code=status, detail=errors) from exc


def _validate_unschedule_payload(body: dict[str, Any] | None) -> UnscheduleRequest:
    try:
        return UnscheduleRequest.model_validate(body or {})
    except ValidationError as exc:
        errors = exc.errors(include_url=False)
        status = 400 if any(e["type"] == "extra_forbidden" for e in errors) else 422
        raise HTTPException(status_code=status, detail=errors) from exc


def _binding_pi_mode_for(name: str) -> str:
    try:
        bindings = _load_bindings(BINDINGS_PATH)
    except (OSError, yaml.YAMLError):
        return "one-shot"
    for binding in bindings:
        if binding.get("name") == name:
            mode = str(binding.get("pi_mode") or "one-shot")
            return mode if mode in {"one-shot", "rpc"} else "one-shot"
    return "one-shot"


def _binding_approval_enabled_for(name: str) -> bool:
    try:
        bindings = _load_bindings(BINDINGS_PATH)
    except (OSError, yaml.YAMLError):
        return False
    for binding in bindings:
        if binding.get("name") == name:
            approval = binding.get("approval")
            return isinstance(approval, dict) and approval.get("enabled") is True
    return False


def _binding_claude_persist_for(name: str) -> bool:
    try:
        bindings = _load_bindings(BINDINGS_PATH)
    except (OSError, yaml.YAMLError):
        return False
    for binding in bindings:
        if binding.get("name") == name:
            return binding.get("claude_persist") is True
    return False


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
    return _decorate_issue_gates(connection, [_row(row)])[0]


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
    current = _decorate_issue_gates(connection, [_row(stored)])[0]

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

    for key in ("blocked_by", "locks"):
        if key in fields and fields[key] is None:
            fields[key] = []

    if fields.get("preferred_skill") is not None:
        _require_known_skill(connection, fields["preferred_skill"])

    if "blocked_by" in fields and _blocked_by_has_cycle(
        connection, issue_id, fields["blocked_by"]
    ):
        raise HTTPException(status_code=400, detail="blocked_by cycle detected")

    # Remote bindings (ADR-0012) defer worktrees: a patch attempting to enable a
    # worktree on a remote binding is coerced to False so the worktree machinery
    # is never engaged against the remote repo_path.
    if fields.get("worktree_active") and _is_remote_binding(
        str(current.get("binding_name") or "")
    ):
        fields["worktree_active"] = False

    # No-op guard: an empty body or a patch echoing stored values must not bump
    # updated_at — the board orders by it, so a blind bump reorders cards.
    changed = {name: value for name, value in fields.items() if current[name] != value}
    if (
        fields.get("state") in ("in_review", "blocked")
        and current.get("inbox_dismissed_at") is not None
    ):
        changed["inbox_dismissed_at"] = None
    if not changed:
        return current

    changed["updated_at"] = _next_updated_at(current["updated_at"])
    stored_changed = changed.copy()
    for key in ("blocked_by", "locks"):
        if key in stored_changed:
            stored_changed[key] = json.dumps(stored_changed[key])
    assignments = ", ".join(f"{name} = ?" for name in stored_changed)
    try:
        connection.execute(
            f"UPDATE issue SET {assignments} WHERE id = ?",
            (*stored_changed.values(), issue_id),
        )
    except sqlite3.IntegrityError as exc:
        # Mirrors create: a duplicate external_id (global UNIQUE, ADR-0015) is a
        # conflict, not a 500 — the caller should reconcile via find_by_external_id.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    connection.commit()

    row = connection.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
    result = _decorate_issue_gates(connection, [_row(row)])[0]
    await websocket_hub.publish(
        {"type": "issue.updated", "id": issue_id, "row": result}
    )
    if changed.get("state") == "todo":
        touch_wake_sentinel()

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


@app.post("/api/issues/{issue_id}/schedule")
async def schedule_issue(
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
    schedule = _validate_schedule_payload(body)

    if _binding_type_for(str(current["binding_name"])) != "infra":
        raise HTTPException(status_code=400, detail="scheduling is infra-only")
    if current["state"] == "archived":
        raise HTTPException(status_code=409, detail="cannot schedule archived issue")
    if current.get("latest_run_state") in ACTIVE_RUN_STATES:
        raise HTTPException(
            status_code=409,
            detail=f"schedule not allowed during run {current['latest_run_state']}",
        )

    now_dt = datetime.now(UTC)
    now = now_dt.isoformat()
    not_before, reason = _resolve_schedule_request(schedule, now_dt)
    appended = "\n\n" + format_schedule_comment(not_before=not_before, reason=reason)
    connection.execute(
        """
        UPDATE issue
           SET comments_md = COALESCE(comments_md, '') || ?,
               scheduled_for = ?,
               state = 'todo',
               updated_at = ?
         WHERE id = ?
        """,
        (appended, now, now, issue_id),
    )
    connection.commit()
    row = connection.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
    result = _row(row)
    await websocket_hub.publish(
        {"type": "issue.updated", "id": issue_id, "row": result}
    )
    touch_wake_sentinel()
    return result


@app.delete("/api/issues/{issue_id}/schedule")
async def unschedule_issue(
    issue_id: int,
    body: dict[str, Any] | None = None,
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, Any]:
    stored = connection.execute(
        "SELECT * FROM issue WHERE id = ?", (issue_id,)
    ).fetchone()
    if stored is None:
        raise HTTPException(status_code=404, detail="issue not found")
    current = _row(stored)
    unschedule = _validate_unschedule_payload(body)

    if _binding_type_for(str(current["binding_name"])) != "infra":
        raise HTTPException(status_code=400, detail="scheduling is infra-only")

    now = datetime.now(UTC).isoformat()
    reason = unschedule.reason or "operator unscheduled via Podium"
    try:
        cancellation = format_cancellation_comment(reason=reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    connection.execute(
        """
        UPDATE issue
           SET comments_md = COALESCE(comments_md, '') || ?,
               scheduled_for = NULL,
               updated_at = ?
         WHERE id = ?
        """,
        ("\n\n" + cancellation, now, issue_id),
    )
    connection.commit()
    row = connection.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
    result = _row(row)
    await websocket_hub.publish(
        {"type": "issue.updated", "id": issue_id, "row": result}
    )
    touch_wake_sentinel()
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
    result = _decorate_issue_gates(connection, [_row(row)])[0]
    await websocket_hub.publish(
        {"type": "issue.updated", "id": issue_id, "row": result}
    )
    touch_wake_sentinel()
    return result


@app.post("/api/issues/{issue_id}/comment")
async def comment_on_issue(
    issue_id: int,
    body: dict[str, Any],
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, Any]:
    """Append-only Comment primitive (ADR-0017).

    Mirrors /reply's append + monotonic updated_at bump + issue.updated publish,
    but drops the three reopen-coupled effects: no state flip to 'todo', no
    run-state gate (works in ANY state — including running — and never 409s on
    state grounds), and no wake-sentinel touch (no re-dispatch). Attribution is
    caller-owned: the body is appended verbatim with no `### …` header, mirroring
    the in-process agent path. Use /reply when you also want reopen + re-dispatch.
    """
    stored = connection.execute(
        "SELECT * FROM issue WHERE id = ?", (issue_id,)
    ).fetchone()
    if stored is None:
        raise HTTPException(status_code=404, detail="issue not found")
    current = _row(stored)

    # A Comment shares Reply's body shape (single non-empty `body`); reuse the
    # model. Unknown key -> 400, empty/invalid value -> 422 (like reply/patch).
    try:
        comment = ReplyCreate.model_validate(body)
    except ValidationError as exc:
        errors = exc.errors(include_url=False)
        for error in errors:
            error.pop("ctx", None)
        status = 400 if any(e["type"] == "extra_forbidden" for e in errors) else 422
        raise HTTPException(status_code=status, detail=errors) from exc

    now = _next_updated_at(current["updated_at"])
    appended = f"\n\n{comment.body.strip()}"  # verbatim, no `### …` header

    # One atomic append + bump. No state clause and no run-state guard: a Comment
    # never reopens and never 409s. COALESCE guards a legacy NULL comments_md.
    cursor = connection.execute(
        """
        UPDATE issue
           SET comments_md = COALESCE(comments_md, '') || ?,
               updated_at = ?
         WHERE id = ?
        """,
        (appended, now, issue_id),
    )
    connection.commit()

    if cursor.rowcount == 0:
        # Row vanished between the SELECT and the UPDATE; with no guard, 409 is
        # impossible, so this is a genuine 404.
        raise HTTPException(status_code=404, detail="issue not found")

    row = connection.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
    result = _decorate_issue_gates(connection, [_row(row)])[0]
    await websocket_hub.publish(
        {"type": "issue.updated", "id": issue_id, "row": result}
    )
    return result


@app.post("/api/issues/{issue_id}/steer")
async def steer_issue(
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

    try:
        steer = SteerCreate.model_validate(body)
    except ValidationError as exc:
        errors = exc.errors(include_url=False)
        status = 400 if any(e["type"] == "extra_forbidden" for e in errors) else 422
        raise HTTPException(status_code=status, detail=errors) from exc

    message = (steer.body or "").strip()
    if steer.action == "steer" and not message:
        raise HTTPException(status_code=422, detail="body cannot be empty for steer")
    if steer.action == "abort" and not message:
        message = "Abort requested."

    run_id = str(current.get("latest_run_id") or "")
    if (
        current.get("state") != "running"
        or current.get("latest_run_state") != "running"
        or not run_id
    ):
        raise HTTPException(
            status_code=409,
            detail="steer requires an active running pi RPC run",
        )

    run = connection.execute("SELECT * FROM run WHERE id = ?", (run_id,)).fetchone()
    if run is None or str(run["state"] or "") != "running":
        raise HTTPException(
            status_code=409,
            detail="steer requires an active running pi RPC run",
        )
    agent = str(run["agent"] or "").strip().lower()
    binding_name = str(current.get("binding_name") or "")
    pi_rpc_enabled = agent == "pi" and _binding_pi_mode_for(binding_name) == "rpc"
    claude_steer_enabled = agent == "claude" and _binding_claude_persist_for(
        binding_name
    )
    if agent == "claude" and not claude_steer_enabled:
        raise HTTPException(
            status_code=409,
            detail="enable claude_persist for live Claude steering",
        )
    if not (pi_rpc_enabled or claude_steer_enabled):
        raise HTTPException(
            status_code=409,
            detail="steer requires an active running pi RPC run",
        )

    now = _next_updated_at(current["updated_at"])
    heading = "Operator Steer" if steer.action == "steer" else "Operator Abort"
    appended = f"\n\n### {heading} ({now})\n\n{message}"
    cursor = connection.execute(
        """
        UPDATE issue
           SET comments_md = COALESCE(comments_md, '') || ?,
               updated_at = ?
         WHERE id = ?
           AND state = 'running'
           AND latest_run_id = ?
           AND latest_run_state = 'running'
        """,
        (appended, now, issue_id, run_id),
    )
    connection.commit()
    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=409,
            detail="steer requires an active running pi RPC run",
        )

    write_steer_record(
        run_id,
        str(issue_id),
        kind=steer.action,
        message=message,
        created_at=now,
    )
    row = connection.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
    result = _row(row)
    await websocket_hub.publish(
        {"type": "issue.updated", "id": issue_id, "row": result}
    )
    return result


async def _clear_worktree_active_remote(
    issue_id: int,
    current: dict[str, Any],
    connection: sqlite3.Connection,
) -> dict[str, Any]:
    """Remote-binding worktree-path shortcut (ADR-0012).

    Remote bindings have no local worktree, so the done-merge / archive-teardown
    / toggle-off helpers must skip all local git/Path ops. They still clear and
    publish ``worktree_active`` for any pre-existing remote row (defense against
    rows that predate the API create/patch coercion), mirroring the column clear
    in ``_maybe_teardown_archived_worktree``."""
    if current.get("worktree_active") is True:
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
            land_worktree,
            worktree_dir,
            worktree_exists,
            worktree_is_dirty,
        )
    except ImportError:  # pragma: no cover - uvicorn --app-dir web/api path
        from worktree import (  # type: ignore[no-redef]
            base_repo_dirty,
            branch_name,
            land_worktree,
            worktree_dir,
            worktree_exists,
            worktree_is_dirty,
        )

    binding_name = current.get("binding_name", "")
    issue_str = str(issue_id)
    base_branch = current.get("base_branch") or "main"

    # Remote bindings (ADR-0012) have no local worktree to merge — the remote
    # agent commits directly in repo_path over SSH. Skip every local git/Path op,
    # but still clear/publish worktree_active for any pre-existing remote row.
    if _is_remote_binding(binding_name):
        return await _clear_worktree_active_remote(issue_id, current, connection)

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

    # ADR-0014: a dirty worktree means the agent left uncommitted work. Never
    # merge/force-remove it (silent data loss). Re-dispatch the agent to commit
    # its own work, capped to avoid an infinite loop; over the cap, block.
    if await asyncio.to_thread(worktree_is_dirty, repo_path, binding_name, issue_str):
        comments_row = connection.execute(
            "SELECT comments_md FROM issue WHERE id = ?", (issue_id,)
        ).fetchone()
        prior = _count_commit_redispatches(comments_row["comments_md"])
        if prior >= MAX_COMMIT_REDISPATCH:
            msg = (
                f"Auto-commit re-dispatch halted: worktree at "
                f"{worktree_dir(repo_path, binding_name, issue_str)} is still "
                f"uncommitted after {MAX_COMMIT_REDISPATCH} re-dispatches. "
                f"Branch {branch_name(binding_name, issue_str)} is unmerged and "
                f"the worktree is intact for manual handling."
            )
            return await _append_blocked_and_publish(connection, issue_id, current, msg)
        return await _redispatch_to_commit(
            connection, issue_id, current, repo_path, binding_name, issue_str
        )

    # Precheck: base checkout must be clean.
    if await asyncio.to_thread(base_repo_dirty, repo_path):
        msg = (
            f"Auto-merge halted: base checkout has uncommitted changes. "
            f"Branch {branch_name(binding_name, issue_str)} is unmerged. "
            f"Worktree at {worktree_dir(repo_path, binding_name, issue_str)} is intact."
        )
        return await _append_blocked_and_publish(connection, issue_id, current, msg)

    error = await asyncio.to_thread(
        land_worktree, repo_path, binding_name, issue_str, base_branch
    )
    if error is not None:
        return await _append_blocked_and_publish(connection, issue_id, current, error)

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
    # Remote bindings (ADR-0012): no local worktree to tear down. Skip the local
    # probe/removal, still clear/publish worktree_active for pre-existing rows.
    if _is_remote_binding(binding_name):
        return await _clear_worktree_active_remote(issue_id, current, connection)

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
    # Remote bindings (ADR-0012): no local worktree exists, so there is nothing
    # to archive and no archive comment to append. Skip local probe, still
    # clear/publish worktree_active for pre-existing rows.
    if _is_remote_binding(binding_name):
        return await _clear_worktree_active_remote(issue_id, current, connection)

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


def _count_commit_redispatches(comments_md: str | None) -> int:
    """Count prior auto-commit re-dispatches recorded in ``comments_md``.

    Each re-dispatch appends one ``COMMIT_REDISPATCH_REPLY_PREFIX`` marker, so a
    plain substring count gives the number of prior attempts. A legacy NULL
    comments_md counts as 0.
    """
    if not comments_md:
        return 0
    return comments_md.count(COMMIT_REDISPATCH_REPLY_PREFIX)


async def _redispatch_to_commit(
    connection: sqlite3.Connection,
    issue_id: int,
    current: dict[str, Any],
    repo_path: Path,
    binding_name: str,
    issue_str: str,
) -> dict[str, Any]:
    """Re-dispatch a dirty worktree's agent to commit its own work (ADR-0014).

    Appends a synthetic ``### Operator Reply (Symphony auto-commit · …)`` note
    instructing the agent to test and commit its existing worktree changes, then
    flips the Issue back to ``todo`` so the scheduler resumes it in the same
    (idempotently preserved) dirty worktree. Leaves the worktree intact — no
    merge, no force-removal. Mirrors ``reply_to_issue`` for the
    append/flip/publish/wake mechanics.
    """
    try:
        from web.api.worktree import branch_name, worktree_dir
    except ImportError:  # pragma: no cover - uvicorn --app-dir web/api path
        from worktree import branch_name, worktree_dir  # type: ignore[no-redef]

    # Re-read fresh comments_md/updated_at: patch_issue already committed
    # state='done' and bumped updated_at before _maybe_merge_worktree ran, so
    # current["updated_at"] is stale. Mirror _append_blocked_and_publish.
    latest = connection.execute(
        "SELECT comments_md, updated_at FROM issue WHERE id = ?", (issue_id,)
    ).fetchone()
    now = _next_updated_at(latest["updated_at"])

    wt_path = worktree_dir(repo_path, binding_name, issue_str)
    branch = branch_name(binding_name, issue_str)
    note = (
        f"\n\n{COMMIT_REDISPATCH_REPLY_PREFIX} · {now})\n\n"
        f"Your worktree at `{wt_path}` (branch `{branch}`) has uncommitted "
        f"changes, but the Issue was marked done with nothing committed — so "
        f"the work cannot be landed and would be lost.\n\n"
        f"Commit only the work that already exists in the worktree: run the "
        f"repo's tests for the changed code, then `git add -A && git commit` "
        f"with a clear message. Do not start new work or expand scope. When the "
        f"commit lands, end your turn."
    )

    cursor = connection.execute(
        """
        UPDATE issue
           SET comments_md = COALESCE(comments_md, '') || ?,
               state = 'todo',
               updated_at = ?
         WHERE id = ?
        """,
        (note, now, issue_id),
    )
    connection.commit()
    assert cursor.rowcount == 1

    row = connection.execute("SELECT * FROM issue WHERE id = ?", (issue_id,)).fetchone()
    result = _row(row)
    await websocket_hub.publish(
        {"type": "issue.updated", "id": issue_id, "row": result}
    )
    touch_wake_sentinel()
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


def _is_remote_binding(name: str) -> bool:
    """True when the binding has a truthy ``remote:`` key in bindings.yml.

    Remote bindings (ADR-0012) run the agent over SSH against a non-local
    ``repo_path``, so every local worktree/git/Path operation must be skipped
    for them. Honors ``_bindings_override`` (test hook) like
    ``_repo_path_for_binding``; any read failure degrades to ``False`` (treat
    as local — the conservative default that preserves existing behavior)."""
    import yaml

    if _bindings_override is not None:
        raw: Any = _bindings_override
    else:
        try:
            raw = _load_bindings(BINDINGS_PATH)
        except (OSError, yaml.YAMLError):
            return False
    for binding in raw if isinstance(raw, list) else raw.get("bindings", []):
        if binding.get("name") == name:
            return bool(binding.get("remote"))
    return False


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

        # Remote bindings (ADR-0012) have no local worktree; skip the local
        # git/Path probe/removal (the remote repo_path is not local).
        if _is_remote_binding(binding_name):
            purged += 1
            continue

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


# Register the file browser/editor router. require_auth (defined above) gates
# all /api/* paths, so these endpoints inherit session-cookie auth.
app.include_router(_files.files_router)
