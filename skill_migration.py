"""Podium-backed helpers for the Symphony operational skill suite.

These helpers are intentionally small and testable. The human-facing
``symphony-*`` skills describe the operator workflow; this module owns the
Podium API/SQLite seams those workflows rely on after Plane retirement.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml

from web.api.db import connect
from web.api.schema import SCHEMA_SQL


class PodiumApiClient(Protocol):
    """Minimal sync client shape shared by FastAPI TestClient and httpx.Client."""

    def get(self, url: str) -> Any: ...
    def post(self, url: str, *, json: Mapping[str, Any]) -> Any: ...


@dataclass(frozen=True)
class PodiumBindingScaffoldRequest:
    name: str
    repo_path: Path
    base_branch: str
    display_name: str | None = None
    color: str = "#888888"
    sort_order: int | None = None
    default_agent: str = "pi"
    binding_type: str = "coding"
    # pi dispatch transport (ADR-0010). Defaults to "rpc" — the accepted
    # standard for all live bindings — and is written only for pi bindings.
    # "one-shot" remains selectable as the legacy `pi --print` rollback path.
    pi_mode: str = "rpc"
    landing_mode: str = "local"
    approval_enabled: bool = False
    context_compact_threshold_tokens: int = 16_000
    context_compact_keep_recent_runs: int = 3


@dataclass(frozen=True)
class PodiumBindingScaffoldResult:
    binding_name: str
    db_path: Path
    bindings_path: Path


@dataclass(frozen=True)
class PodiumBindingRemovalResult:
    binding_name: str
    removed_from_bindings_yml: bool
    db_action: str  # "archived" | "deleted" | "absent"
    deleted_issue_count: int
    deleted_run_count: int


def scaffold_podium_binding(
    request: PodiumBindingScaffoldRequest,
    *,
    db_path: Path,
    bindings_path: Path,
) -> PodiumBindingScaffoldResult:
    """Create a Podium binding row and append a tracker=podium binding.

    No Plane API, Plane transport, or ``plane_adapter`` dependency is involved.
    ``plane_project_id`` remains in bindings.yml only because the current
    ``ProjectBinding`` config shape still requires it during the Podium cutover.
    """

    _validate_binding_name(request.name)
    if request.default_agent not in {"pi", "claude"}:
        raise ValueError("default_agent must be 'pi' or 'claude'")
    if request.binding_type not in {"infra", "coding"}:
        raise ValueError("binding_type must be 'infra' or 'coding'")
    if request.pi_mode not in {"one-shot", "rpc"}:
        raise ValueError("pi_mode must be 'one-shot' or 'rpc'")

    with connect(db_path) as connection:
        _ensure_schema(connection)
        _insert_binding_row(connection, request)

    binding = {
        "name": request.name,
        # Transitional compatibility with ProjectBinding/config.py.
        "plane_project_id": request.name,
        "tracker": "podium",
        "type": request.binding_type,
        "repo_path": str(request.repo_path),
        "base_branch": request.base_branch,
        "default_agent": request.default_agent,
        "approval": {"enabled": request.approval_enabled},
        "landing": {"mode": request.landing_mode},
    }
    # pi_mode only governs pi dispatch; omit it for claude bindings.
    if request.default_agent == "pi":
        binding["pi_mode"] = request.pi_mode
    _append_binding(bindings_path, binding)
    return PodiumBindingScaffoldResult(
        binding_name=request.name,
        db_path=db_path,
        bindings_path=bindings_path,
    )


def remove_podium_binding(
    name: str,
    *,
    db_path: Path,
    bindings_path: Path,
    purge: bool = False,
) -> PodiumBindingRemovalResult:
    """Remove a Symphony binding. Inverse of ``scaffold_podium_binding``.

    Default (``purge=False``) is reversible: the binding row is archived
    (``archived = TRUE``) and its ``bindings.yml`` entry is dropped, which stops
    the dispatch loop from picking it up while preserving Issue/Run history.

    ``purge=True`` is destructive: it deletes the binding's Runs, Issues,
    ``binding_settings`` row, and ``binding`` row, then drops the ``bindings.yml``
    entry. Use only when history is not worth keeping.

    No Plane API, Plane transport, or ``plane_adapter`` dependency is involved.
    """

    _validate_binding_name(name)

    removed_from_yaml = _remove_binding(bindings_path, name)

    db_action = "absent"
    deleted_issue_count = 0
    deleted_run_count = 0
    with connect(db_path) as connection:
        _ensure_schema(connection)
        exists = connection.execute(
            "SELECT name FROM binding WHERE name = ?", (name,)
        ).fetchone()
        if exists is not None:
            if purge:
                deleted_run_count = connection.execute(
                    """
                    DELETE FROM run WHERE issue_id IN (
                      SELECT id FROM issue WHERE binding_name = ?
                    )
                    """,
                    (name,),
                ).rowcount
                deleted_issue_count = connection.execute(
                    "DELETE FROM issue WHERE binding_name = ?", (name,)
                ).rowcount
                connection.execute("DELETE FROM binding WHERE name = ?", (name,))
                db_action = "deleted"
            else:
                connection.execute(
                    "UPDATE binding SET archived = TRUE WHERE name = ?", (name,)
                )
                db_action = "archived"
            connection.commit()

    if not removed_from_yaml and db_action == "absent":
        raise ValueError(
            f"binding not found in bindings.yml or Podium DB: {name}"
        )

    return PodiumBindingRemovalResult(
        binding_name=name,
        removed_from_bindings_yml=removed_from_yaml,
        db_action=db_action,
        deleted_issue_count=deleted_issue_count,
        deleted_run_count=deleted_run_count,
    )


def create_podium_smoke_issue(
    client: PodiumApiClient,
    binding_name: str,
    *,
    title: str,
    description: str = "Symphony binding smoke test. No code changes expected.",
    preferred_skill: str | None = None,
    preferred_agent: str | None = "pi",
    worktree_active: bool = False,
) -> dict[str, Any]:
    """Create a low-risk smoke Issue through Podium, not Plane."""

    payload: dict[str, Any] = {
        "title": title,
        "description": description,
        "preferred_agent": preferred_agent,
        "worktree_active": worktree_active,
    }
    if preferred_skill is not None:
        payload["preferred_skill"] = preferred_skill
    response = client.post(f"/api/bindings/{binding_name}/issues", json=payload)
    _raise_for_status(response)
    return dict(response.json())


def poll_podium_issue_run(
    client: PodiumApiClient,
    issue_id: int,
    *,
    timeout_seconds: float = 180.0,
    interval_seconds: float = 1.0,
) -> dict[str, Any] | None:
    """Poll Podium Run rows for an Issue until at least one Run exists."""

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() <= deadline:
        response = client.get(f"/api/issues/{issue_id}/runs")
        _raise_for_status(response)
        runs = list(response.json())
        if runs:
            return dict(runs[0])
        time.sleep(interval_seconds)
    return None


def podium_bindings_status(client: PodiumApiClient) -> list[dict[str, Any]]:
    """Return status rows using Podium bindings + per-binding Issues."""

    bindings_response = client.get("/api/bindings")
    _raise_for_status(bindings_response)
    rows: list[dict[str, Any]] = []
    for binding in bindings_response.json():
        name = str(binding["name"])
        issues_response = client.get(f"/api/bindings/{name}/issues")
        _raise_for_status(issues_response)
        issues = list(issues_response.json())
        open_issues = [issue for issue in issues if issue.get("state") != "done"]
        latest = issues[0] if issues else None
        rows.append(
            {
                "name": name,
                "display_name": binding.get("display_name"),
                "open_issue_count": len(open_issues),
                "latest_issue_state": latest.get("state") if latest else None,
                "latest_run_state": latest.get("latest_run_state") if latest else None,
            }
        )
    return rows


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    connection.commit()


def _insert_binding_row(
    connection: sqlite3.Connection, request: PodiumBindingScaffoldRequest
) -> None:
    existing = connection.execute(
        "SELECT name FROM binding WHERE name = ?", (request.name,)
    ).fetchone()
    if existing is not None:
        raise ValueError(f"binding already exists in Podium: {request.name}")
    connection.execute(
        """
        INSERT INTO binding(name, display_name, color, sort_order, archived)
        VALUES (?, ?, ?, ?, FALSE)
        """,
        (
            request.name,
            request.display_name or request.name,
            request.color,
            request.sort_order,
        ),
    )
    connection.execute(
        """
        INSERT INTO binding_settings(
          binding_name, context_compact_threshold_tokens, context_compact_keep_recent_runs
        ) VALUES (?, ?, ?)
        """,
        (
            request.name,
            request.context_compact_threshold_tokens,
            request.context_compact_keep_recent_runs,
        ),
    )
    connection.commit()


def _append_binding(path: Path, binding: dict[str, Any]) -> None:
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        raw = None
    if raw is None:
        raw = {"bindings": []}
    if not isinstance(raw, dict) or not isinstance(raw.get("bindings"), list):
        raise ValueError(f"{path}: expected mapping with bindings list")
    for existing in raw["bindings"]:
        if isinstance(existing, dict) and existing.get("name") == binding["name"]:
            raise ValueError(
                f"binding already exists in bindings.yml: {binding['name']}"
            )
    raw["bindings"].append(binding)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def _remove_binding(path: Path, name: str) -> bool:
    """Drop the binding entry named ``name`` from bindings.yml.

    Returns True if an entry was removed, False if the file or entry is absent.
    """
    if not path.exists():
        return False
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("bindings"), list):
        raise ValueError(f"{path}: expected mapping with bindings list")
    kept = [
        b
        for b in raw["bindings"]
        if not (isinstance(b, dict) and b.get("name") == name)
    ]
    if len(kept) == len(raw["bindings"]):
        return False
    raw["bindings"] = kept
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return True


def _validate_binding_name(name: str) -> None:
    if not name or any(char.isspace() for char in name):
        raise ValueError("binding name must be non-empty and contain no whitespace")


def _raise_for_status(response: Any) -> None:
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
        return
    status_code = getattr(response, "status_code", 200)
    if status_code >= 400:
        raise RuntimeError(f"Podium API request failed: HTTP {status_code}")
