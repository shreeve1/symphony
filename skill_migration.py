"""Podium-backed helpers for the Symphony operational skill suite.

These helpers are intentionally small and testable. The human-facing
``symphony-*`` skills describe the operator workflow; this module owns the
Podium API/SQLite seams those workflows rely on after Plane retirement.
"""

from __future__ import annotations

import re
import sqlite3
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import yaml

from web.api.db import connect
from web.api.schema import SCHEMA_SQL


class PodiumApiClient(Protocol):
    """Minimal sync client shape shared by FastAPI TestClient and httpx.Client."""

    def get(self, url: str) -> Any: ...
    def post(self, url: str, *, json: Mapping[str, Any]) -> Any: ...
    def patch(self, url: str, *, json: Mapping[str, Any]) -> Any: ...


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
    # Remote execution target (ADR-0012). remote_host is the host name used for
    # SSH and sidebar grouping; do not depend on reverse DNS for display.
    remote_host: str | None = None
    remote_user: str | None = None
    remote_identity: str | None = None
    # Display-only sidebar grouping label (ADR-0039). When omitted, the scaffold
    # auto-detects an existing binding on the same host+user and backfills a
    # shared alias onto both bindings so they collapse under one sidebar header.
    remote_host_alias: str | None = None


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

    is_remote = request.remote_host is not None or request.remote_user is not None
    host_alias: str | None = None
    backfill_targets: list[str] = []
    if is_remote:
        # Mirror config.py remote v1 constraints so scaffolding fails fast
        # rather than producing a bindings.yml entry config.py would reject.
        if request.remote_host is None or request.remote_user is None:
            raise ValueError("remote bindings require both remote_host and remote_user")
        if request.binding_type != "coding":
            raise ValueError("remote bindings require binding_type 'coding' (v1)")
        if request.default_agent != "pi":
            raise ValueError("remote bindings require default_agent 'pi' (v1)")
        if request.pi_mode != "rpc":
            raise ValueError("remote bindings require pi_mode 'rpc'")
        # Resolve the display-only sidebar grouping alias (ADR-0039) against the
        # bindings already on this host+user, and note which of them need the
        # alias backfilled so siblings collapse under one sidebar header.
        existing = _read_bindings_list(bindings_path)
        host_alias, backfill_targets = _resolve_host_alias(request, existing)

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
    if is_remote:
        remote: dict[str, str] = {
            "host": cast(str, request.remote_host),
            "user": cast(str, request.remote_user),
        }
        if request.remote_identity is not None:
            remote["identity"] = request.remote_identity
        if host_alias is not None:
            remote["host_alias"] = host_alias
        binding["remote"] = remote
    _append_binding(bindings_path, binding)
    if host_alias is not None:
        for target in backfill_targets:
            _backfill_remote_host_alias(bindings_path, target, host_alias)
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
                # issue.latest_run_id and run.issue_id reference each other, so
                # no single delete order satisfies the cycle while foreign_keys
                # is ON (db.connect enables it). Defer FK checks to commit, by
                # which point every row in the cycle is gone.
                connection.execute("PRAGMA defer_foreign_keys = ON")
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
        raise ValueError(f"binding not found in bindings.yml or Podium DB: {name}")

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
        "description": description,
        "preferred_agent": preferred_agent,
        "worktree_active": worktree_active,
    }
    if preferred_skill is not None:
        payload["preferred_skill"] = preferred_skill
    response = client.post(f"/api/bindings/{binding_name}/issues", json=payload)
    _raise_for_status(response)
    issue_data = dict(response.json())

    # Patch the title afterward
    patch_response = client.patch(
        f"/api/issues/{issue_data['id']}", json={"title": title}
    )
    _raise_for_status(patch_response)
    return dict(patch_response.json())


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


def _read_bindings_list(path: Path) -> list[dict[str, Any]]:
    """Return the bindings list from bindings.yml, or [] when absent/empty."""
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return []
    if not isinstance(raw, dict) or not isinstance(raw.get("bindings"), list):
        raise ValueError(f"{path}: expected mapping with bindings list")
    return [b for b in raw["bindings"] if isinstance(b, dict)]


def _resolve_host_alias(
    request: PodiumBindingScaffoldRequest, existing: list[dict[str, Any]]
) -> tuple[str | None, list[str]]:
    """Resolve the display-only sidebar grouping alias for a remote binding.

    Returns ``(host_alias, backfill_targets)`` (ADR-0039):

    - Explicit ``remote_host_alias`` on the request wins; every sibling binding
      on the same host+user that lacks it (or differs) is a backfill target.
    - Otherwise, if any sibling on the same host+user already carries a
      ``host_alias``, reuse it; siblings missing it are backfill targets.
    - Otherwise, if siblings exist but none is aliased, derive an alias from a
      sibling's ``display_name``/``name`` (lowercased) and backfill it onto all
      of them so they collapse under one header.
    - Otherwise (no sibling on this host) return ``(None, [])`` — a solo remote
      binding needs no alias; the existing frontend fallback handles it.
    """

    def _siblings() -> list[dict[str, Any]]:
        matches = []
        for b in existing:
            remote = b.get("remote")
            if not isinstance(remote, dict):
                continue
            if (
                remote.get("host") == request.remote_host
                and remote.get("user") == request.remote_user
            ):
                matches.append(b)
        return matches

    siblings = _siblings()

    if request.remote_host_alias is not None:
        alias = request.remote_host_alias.lower()
    else:
        if not siblings:
            return None, []
        alias = None
        for b in siblings:
            remote = b["remote"]
            if isinstance(remote, dict) and remote.get("host_alias"):
                alias = str(remote["host_alias"]).lower()
                break
        if alias is None:
            source = siblings[0]
            alias = str(source.get("display_name") or source.get("name")).lower()

    backfill_targets = [
        str(b["name"])
        for b in siblings
        if not (
            isinstance(b.get("remote"), dict)
            and str(b["remote"].get("host_alias") or "").lower() == alias
        )
    ]
    return alias, backfill_targets


def _backfill_remote_host_alias(path: Path, name: str, host_alias: str) -> None:
    """Insert ``remote.host_alias`` into an existing binding's ``remote:`` block.

    Byte-preserving, like ``_append_binding``: a load/dump rewrite would flatten
    indentation and drop comments (the live n8n block carries the NetBird sshd
    caveat), turning a one-line add into a whole-file diff that trips restart
    pre-sanity. Instead this scans for the named binding's ``remote:`` block and
    splices one ``host_alias:`` line under it, matching the block's key indent.
    Callers backfill only when merging sibling bindings under one sidebar header
    (ADR-0039).
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    name_re = re.compile(r"^(\s*)-\s+name:\s*(.+?)\s*$")
    item_indent: str | None = None
    in_target = False
    remote_indent: str | None = None
    key_indent: str | None = None
    insert_at: int | None = None
    for i, line in enumerate(lines):
        m = name_re.match(line)
        if m:
            if in_target and remote_indent is not None:
                insert_at = i
                break
            item_indent = m.group(1)
            in_target = m.group(2).strip().strip("'\"") == name
            remote_indent = None
            continue
        if not in_target:
            continue
        if remote_indent is None:
            rm = re.match(r"^(\s*)remote:\s*$", line)
            if rm and (item_indent is None or len(rm.group(1)) > len(item_indent)):
                remote_indent = rm.group(1)
            continue
        if line.strip() == "":
            continue
        cur_indent = line[: len(line) - len(line.lstrip())]
        if len(cur_indent) <= len(remote_indent):
            insert_at = i
            break
        if re.match(r"^\s*host_alias:", line):
            return  # already present
        key_indent = cur_indent
        insert_at = i + 1
    if remote_indent is None:
        raise ValueError(f"binding {name} is not remote; cannot set host_alias")
    if key_indent is None:
        key_indent = remote_indent + "  "
    if insert_at is None:
        insert_at = len(lines)
    if insert_at > 0 and not lines[insert_at - 1].endswith("\n"):
        lines[insert_at - 1] = lines[insert_at - 1] + "\n"
    lines.insert(insert_at, f"{key_indent}host_alias: {host_alias}\n")
    path.write_text("".join(lines), encoding="utf-8")


def _append_binding(path: Path, binding: dict[str, Any]) -> None:
    # Preserve the existing file byte-for-byte: only the new block is appended.
    # A load/dump/rewrite flattens indentation and drops comments/blank lines,
    # turning a one-binding append into a whole-file diff that trips restart
    # pre-sanity. Dupe and shape checks still parse read-only.
    if path.exists():
        text = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text)
    else:
        text = None
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
    # Fresh/empty file: start a block-style header, append at 0 indent.
    # Non-empty file: keep its text verbatim and match its list-item indent.
    if not raw.get("bindings"):
        base = "bindings:\n"
        indent = ""
    else:
        assert text is not None  # non-empty bindings imply the file existed
        base = text if text.endswith("\n") else text + "\n"
        m = re.search(r"^(\s*)-\s+name:", text or "", flags=re.MULTILINE)
        indent = m.group(1) if m else ""
    block = yaml.safe_dump([binding], sort_keys=False, default_flow_style=False)
    if indent:
        block = "".join(
            indent + line if line.strip() else line
            for line in block.splitlines(keepends=True)
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(base + block, encoding="utf-8")


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
