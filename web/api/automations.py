"""Binding-scoped automations CRUD (ADR-0038, issue #4).

Separate router per issue spec: spawn/loop automation management surface.
No fire/dispatch behaviour, no scheduler integration — pure CRUD.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import sqlite3
from typing import Annotated, Any, Literal

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PositiveInt

from web.api.db import get_connection
from web.api.seed import BINDINGS_PATH, _load_bindings

router = APIRouter(tags=["automations"])


# ── helpers ────────────────────────────────────────────────────────────────


def _get_binding_or_404(connection: sqlite3.Connection, name: str) -> None:
    row = connection.execute(
        "SELECT name FROM binding WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="binding not found")


def _row(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    # bool serialization: SQLite stores booleans as 0/1
    for field in ("enabled", "worktree_active"):
        if field in result and result[field] is not None:
            result[field] = bool(result[field])
    return result


def _loop_eligible(name: str) -> bool:
    """Return whether the binding can preserve a per-Issue worktree."""
    try:
        bindings = _load_bindings(BINDINGS_PATH)
    except (OSError, yaml.YAMLError):
        return False
    for binding in bindings:
        if binding.get("name") == name:
            return (
                binding.get("type") == "coding"
                and not binding.get("remote")
                and binding.get("worktree_default") is not False
            )
    return False


def _validate_completion_marker(value: str) -> str:
    """Reject empty, absolute, or path-traversal completion markers."""
    stripped = value.strip()
    if not stripped:
        raise ValueError("loop_completion_marker must be non-empty")
    if stripped.startswith("/"):
        raise ValueError("loop_completion_marker must be a relative path")
    if ".." in stripped.split("/"):
        raise ValueError("loop_completion_marker must not contain path traversal")
    return stripped


# ── Pydantic models ────────────────────────────────────────────────────────

CompletionMarker = Annotated[str, AfterValidator(_validate_completion_marker)]


class AutomationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["spawn", "loop"]
    enabled: bool = True
    template_title: str = Field(min_length=1)
    template_body: str = Field(min_length=1)
    spawn_interval_seconds: PositiveInt | None = None
    spawn_run_count: PositiveInt | None = None
    # Issue #462: optional one-shot delay before the first spawn fire. Only
    # meaningful at create time (spawn only) — the API computes next_fire_at =
    # now + delay for the INSERT rather than storing a column. Omitted / "start
    # immediately" leaves next_fire_at NULL, which fires on the next tick.
    start_delay_seconds: PositiveInt | None = None
    loop_iteration_cap: PositiveInt | None = None
    loop_completion_marker: CompletionMarker = "DONE.md"
    # Per-Issue dispatch pins (issue #459). Each nullable; the fire path
    # threads them into insert_issue_row so a cadence can pin model/skill/etc.
    # without authoring a throwaway Issue first.
    preferred_skill: str | None = None
    preferred_agent: str | None = None
    preferred_model: str | None = None
    reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None
    ) = None
    base_branch: str | None = None
    worktree_active: bool = False


class AutomationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    template_title: str | None = Field(default=None, min_length=1)
    template_body: str | None = Field(default=None, min_length=1)
    spawn_interval_seconds: PositiveInt | None = None
    spawn_run_count: PositiveInt | None = None
    # Issue #462: reschedule the next spawn fire on edit. start_immediately
    # resets next_fire_at to NULL (fires next tick); start_delay_seconds sets
    # next_fire_at = now + delay. Spawn only; both omitted = leave unchanged.
    start_immediately: bool | None = None
    start_delay_seconds: PositiveInt | None = None
    loop_iteration_cap: PositiveInt | None = None
    loop_completion_marker: CompletionMarker | None = None
    preferred_skill: str | None = None
    preferred_agent: str | None = None
    preferred_model: str | None = None
    reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None
    ) = None
    base_branch: str | None = None
    worktree_active: bool | None = None


# ── endpoint helpers ───────────────────────────────────────────────────────


def _validate_create_for_mode(binding_name: str, body: AutomationCreate) -> None:
    """Validate mode-specific requirements for create."""
    if body.mode == "spawn":
        if body.spawn_interval_seconds is None:
            raise HTTPException(
                status_code=422,
                detail="spawn_interval_seconds is required for spawn mode",
            )
    elif body.mode == "loop":
        # Issue #462: start_delay_seconds governs the first spawn fire; it has
        # no meaning for loops (which fire per completion), so reject it here.
        if body.start_delay_seconds is not None:
            raise HTTPException(
                status_code=422,
                detail="start_delay_seconds is only valid for spawn mode",
            )
        if body.loop_iteration_cap is None:
            raise HTTPException(
                status_code=422,
                detail="loop_iteration_cap is required for loop mode",
            )
        if not _loop_eligible(binding_name):
            raise HTTPException(
                status_code=422,
                detail="loop mode requires a coding binding with persistent worktree capability",
            )
        # Issue #461 (Q4): loops always run inside a persistent worktree.
        # worktree_active=False on a loop is dead state — fire path forces
        # True regardless — so reject explicit `false` rather than silently
        # ignoring the operator's intent. Pydantic's default is False, so
        # we gate on model_fields_set to avoid rejecting the default value
        # when the form omits the field.
        if "worktree_active" in body.model_fields_set and body.worktree_active is False:
            raise HTTPException(
                status_code=422,
                detail="worktree_active must be true for loop mode; loop automations always use a persistent worktree (Q4)",
            )


# ── build SET clause from non-None fields ──────────────────────────────────


def _build_patch_set(
    connection: sqlite3.Connection,
    binding_name: str,
    automation_id: int,
    body: AutomationPatch,
) -> tuple[list[str], list[Any]]:
    sets: list[str] = []
    params: list[Any] = []

    # Fetch current row for mode-aware validation
    current = connection.execute(
        "SELECT * FROM automation WHERE id = ? AND binding_name = ?",
        (automation_id, binding_name),
    ).fetchone()
    if current is None:
        raise HTTPException(status_code=404, detail="automation not found")
    current_mode = str(current["mode"])

    # Build SET list for non-None fields. spawn_run_count and base_branch
    # carry "unlimited / fall back to binding default" semantics when None,
    # so an explicit None in the PATCH payload is honoured instead of being
    # treated as a missing field.
    nullable_patch_fields = {"spawn_run_count", "base_branch"}
    for field in (
        "enabled",
        "template_title",
        "template_body",
        "spawn_interval_seconds",
        "spawn_run_count",
        "loop_iteration_cap",
        "loop_completion_marker",
        "preferred_skill",
        "preferred_agent",
        "preferred_model",
        "reasoning_effort",
        "base_branch",
        "worktree_active",
    ):
        val = getattr(body, field, None)
        explicitly_set = field in body.model_fields_set
        if val is not None or (explicitly_set and field in nullable_patch_fields):
            sets.append(f"{field} = ?")
            params.append(val)

    # Issue #462: reschedule the next fire (spawn only). start_immediately wins
    # (next_fire_at = NULL); else a positive start_delay_seconds sets
    # next_fire_at = now + delay. Both omitted leaves next_fire_at untouched.
    scheduling_requested = (
        "start_immediately" in body.model_fields_set
        or "start_delay_seconds" in body.model_fields_set
    )
    if scheduling_requested:
        if current_mode != "spawn":
            raise HTTPException(
                status_code=422,
                detail="start_immediately/start_delay_seconds are only valid for spawn mode",
            )
        if body.start_immediately:
            sets.append("next_fire_at = ?")
            params.append(None)
        elif body.start_delay_seconds is not None:
            sets.append("next_fire_at = ?")
            params.append(
                (
                    datetime.now(UTC) + timedelta(seconds=body.start_delay_seconds)
                ).isoformat()
            )

    if not sets:
        raise HTTPException(status_code=400, detail="no fields to update")

    if current_mode == "loop" and not _loop_eligible(binding_name):
        raise HTTPException(
            status_code=422,
            detail="loop mode requires a coding binding with persistent worktree capability",
        )
    # Issue #461 (Q4): worktree_active is dead state on loop rows; reject
    # explicit PATCHes rather than store a value the fire path will
    # silently override.
    if (
        current_mode == "loop"
        and "worktree_active" in body.model_fields_set
        and body.worktree_active is False
    ):
        raise HTTPException(
            status_code=422,
            detail="worktree_active must be true for loop mode; loop automations always use a persistent worktree (Q4)",
        )

    return sets, params


# ── endpoints ──────────────────────────────────────────────────────────────


@router.get("/api/bindings/{name}/automations")
def list_automations(
    name: str,
    connection: sqlite3.Connection = Depends(get_connection),
) -> list[dict[str, Any]]:
    _get_binding_or_404(connection, name)
    rows = connection.execute(
        "SELECT * FROM automation WHERE binding_name = ? ORDER BY created_at, id",
        (name,),
    ).fetchall()
    return [_row(row) for row in rows]


@router.post("/api/bindings/{name}/automations", status_code=201)
def create_automation(
    name: str,
    body: dict[str, Any],
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, Any]:
    _get_binding_or_404(connection, name)

    from pydantic import ValidationError

    try:
        payload = AutomationCreate.model_validate(body)
    except ValidationError as exc:
        errors = exc.errors(include_url=False, include_context=False)
        status = 400 if any(e["type"] == "extra_forbidden" for e in errors) else 422
        raise HTTPException(status_code=status, detail=errors) from exc

    _validate_create_for_mode(name, payload)

    now_dt = datetime.now(UTC)
    now = now_dt.isoformat()
    # Issue #462: an optional start delay pushes the first fire out by N seconds.
    # Without it, next_fire_at stays NULL and the fire path fires on the next
    # tick ("start immediately"). The delay is a create-time convenience — the
    # fire path (next_fire_at <= now gate) and compute_next_fire need no change.
    next_fire_at = (
        (now_dt + timedelta(seconds=payload.start_delay_seconds)).isoformat()
        if payload.start_delay_seconds is not None
        else None
    )
    cursor = connection.execute(
        """
        INSERT INTO automation(
          binding_name, mode, enabled,
          template_title, template_body,
          spawn_interval_seconds, spawn_run_count,
          occurrences_fired, next_fire_at,
          loop_iteration_cap, loop_completion_marker,
          preferred_skill, preferred_agent, preferred_model,
          reasoning_effort, base_branch, worktree_active,
          created_at, updated_at
        ) VALUES (
          ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?,
          ?, ?, ?, ?, ?, ?,
          ?, ?
        )
        """,
        (
            name,
            payload.mode,
            payload.enabled,
            payload.template_title,
            payload.template_body,
            payload.spawn_interval_seconds,
            payload.spawn_run_count,
            next_fire_at,
            payload.loop_iteration_cap,
            payload.loop_completion_marker,
            payload.preferred_skill,
            payload.preferred_agent,
            payload.preferred_model,
            payload.reasoning_effort,
            payload.base_branch,
            payload.worktree_active,
            now,
            now,
        ),
    )
    connection.commit()
    row = connection.execute(
        "SELECT * FROM automation WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return _row(row)


@router.get("/api/bindings/{name}/automations/{automation_id}")
def get_automation(
    name: str,
    automation_id: int,
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, Any]:
    _get_binding_or_404(connection, name)
    row = connection.execute(
        "SELECT * FROM automation WHERE id = ? AND binding_name = ?",
        (automation_id, name),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="automation not found")
    return _row(row)


@router.patch("/api/bindings/{name}/automations/{automation_id}")
def patch_automation(
    name: str,
    automation_id: int,
    body: dict[str, Any],
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, Any]:
    _get_binding_or_404(connection, name)

    from pydantic import ValidationError

    try:
        payload = AutomationPatch.model_validate(body)
    except ValidationError as exc:
        errors = exc.errors(include_url=False, include_context=False)
        status = 400 if any(e["type"] == "extra_forbidden" for e in errors) else 422
        raise HTTPException(status_code=status, detail=errors) from exc

    sets, params = _build_patch_set(connection, name, automation_id, payload)
    params.append(datetime.now(UTC).isoformat())
    params.append(automation_id)
    params.append(name)

    connection.execute(
        f"UPDATE automation SET {', '.join(sets)}, updated_at = ?"
        " WHERE id = ? AND binding_name = ?",
        tuple(params),
    )
    connection.commit()

    row = connection.execute(
        "SELECT * FROM automation WHERE id = ?", (automation_id,)
    ).fetchone()
    return _row(row)


@router.delete("/api/bindings/{name}/automations/{automation_id}")
def delete_automation(
    name: str,
    automation_id: int,
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, bool]:
    _get_binding_or_404(connection, name)
    row = connection.execute(
        "SELECT id FROM automation WHERE id = ? AND binding_name = ?",
        (automation_id, name),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="automation not found")
    connection.execute("DELETE FROM automation WHERE id = ?", (automation_id,))
    connection.commit()
    return {"deleted": True}
