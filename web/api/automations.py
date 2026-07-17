"""Binding-scoped automations CRUD (ADR-0038, issue #4).

Separate router per issue spec: spawn/loop automation management surface.
No fire/dispatch behaviour, no scheduler integration — pure CRUD.
"""

from __future__ import annotations

from datetime import UTC, datetime
import sqlite3
from typing import Any, Literal

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    if "enabled" in result and result["enabled"] is not None:
        result["enabled"] = bool(result["enabled"])
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


class AutomationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["spawn", "loop"]
    enabled: bool = True
    template_title: str = Field(min_length=1)
    template_body: str = Field(min_length=1)
    spawn_interval_seconds: int | None = None
    spawn_run_count: int | None = None
    loop_iteration_cap: int | None = None
    loop_completion_marker: str = "DONE.md"

    @field_validator("spawn_interval_seconds")
    @classmethod
    def _spawn_interval_positive(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("spawn_interval_seconds must be positive")
        return v

    @field_validator("spawn_run_count")
    @classmethod
    def _spawn_run_count_positive(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("spawn_run_count must be positive when supplied")
        return v

    @field_validator("loop_iteration_cap")
    @classmethod
    def _loop_cap_positive(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("loop_iteration_cap must be positive")
        return v

    @field_validator("loop_completion_marker")
    @classmethod
    def _loop_marker_safe(cls, v: str) -> str:
        return _validate_completion_marker(v)


class AutomationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    template_title: str | None = Field(default=None, min_length=1)
    template_body: str | None = Field(default=None, min_length=1)
    mode: Literal["spawn", "loop"] | None = None
    spawn_interval_seconds: int | None = None
    spawn_run_count: int | None = None
    loop_iteration_cap: int | None = None
    loop_completion_marker: str | None = None

    @field_validator("spawn_interval_seconds")
    @classmethod
    def _spawn_interval_positive(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("spawn_interval_seconds must be positive")
        return v

    @field_validator("spawn_run_count")
    @classmethod
    def _spawn_run_count_positive(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("spawn_run_count must be positive when supplied")
        return v

    @field_validator("loop_iteration_cap")
    @classmethod
    def _loop_cap_positive(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("loop_iteration_cap must be positive")
        return v

    @field_validator("loop_completion_marker")
    @classmethod
    def _loop_marker_safe(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_completion_marker(v)

    @field_validator("mode")
    @classmethod
    def _mode_immutable(cls, v: str | None) -> str | None:
        if v is not None:
            raise ValueError("mode is immutable after creation")
        return v


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


def _validate_patch_for_mode(
    binding_name: str | None,
    current_mode: str,
    changed: AutomationPatch,
) -> None:
    """Validate mode-specific patch constraints using existing automation mode."""
    effective_mode = changed.mode if changed.mode is not None else current_mode
    mode = effective_mode

    if mode == "spawn":
        if (
            changed.spawn_interval_seconds is not None
            and changed.spawn_interval_seconds < 1
        ):
            raise HTTPException(
                status_code=422,
                detail="spawn_interval_seconds must be positive",
            )
    elif mode == "loop":
        if changed.loop_iteration_cap is not None and changed.loop_iteration_cap < 1:
            raise HTTPException(
                status_code=422,
                detail="loop_iteration_cap must be positive",
            )
        if changed.loop_completion_marker is not None:
            try:
                _validate_completion_marker(changed.loop_completion_marker)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        if binding_name and not _loop_eligible(binding_name):
            raise HTTPException(
                status_code=422,
                detail="loop mode requires a coding binding with persistent worktree capability",
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

    # Build SET list for non-None fields
    for field in (
        "enabled",
        "template_title",
        "template_body",
        "spawn_interval_seconds",
        "spawn_run_count",
        "loop_iteration_cap",
        "loop_completion_marker",
    ):
        val = getattr(body, field, None)
        if val is not None or (
            field == "spawn_run_count" and field in body.model_fields_set
        ):
            sets.append(f"{field} = ?")
            params.append(val)

    if not sets:
        raise HTTPException(status_code=400, detail="no fields to update")

    # Validate mode-specific constraints on the patched values
    _validate_patch_for_mode(binding_name, current_mode, body)

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

    now = datetime.now(UTC).isoformat()
    cursor = connection.execute(
        """
        INSERT INTO automation(
          binding_name, mode, enabled,
          template_title, template_body,
          spawn_interval_seconds, spawn_run_count,
          occurrences_fired, next_fire_at,
          loop_iteration_cap, loop_completion_marker,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?, ?, ?)
        """,
        (
            name,
            payload.mode,
            payload.enabled,
            payload.template_title,
            payload.template_body,
            payload.spawn_interval_seconds,
            payload.spawn_run_count,
            payload.loop_iteration_cap,
            payload.loop_completion_marker,
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
