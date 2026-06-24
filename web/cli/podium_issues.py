"""Create Podium issues from an LLM-sliced plan spec.

The /podium-issues skill does the natural-language slicing. This module is the
boring sink: resolve the Podium binding for cwd, then insert the already-sliced
issues in dependency order so blocked_by contains real Podium ids.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import yaml

_db = cast(Any, import_module("web.api.db"))
_seed = cast(Any, import_module("web.api.seed"))
connect = _db.connect
BINDINGS_PATH = _seed.BINDINGS_PATH


class PodiumIssuesError(RuntimeError):
    """Raised for operator-facing failures."""


@dataclass(frozen=True)
class PlanSlice:
    key: str
    title: str
    description: str
    acceptance: list[str]
    verification: str
    blocked_by: list[str]
    locks: list[str]
    priority: int | None = None


def _git_toplevel(cwd: Path) -> Path:
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(out.stdout.strip()).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return cwd.resolve()


def resolve_binding_for_cwd(
    cwd: Path, bindings_path: Path = BINDINGS_PATH
) -> dict[str, Any]:
    root = _git_toplevel(cwd)
    bindings = _seed._load_bindings(bindings_path)
    podium = [b for b in bindings if str(b.get("tracker")) == "podium"]
    for binding in podium:
        repo_path = binding.get("repo_path")
        if repo_path and Path(repo_path).resolve() == root:
            return binding
    names = ", ".join(sorted(str(b["name"]) for b in podium)) or "(none)"
    raise PodiumIssuesError(
        f"no podium binding matches {root}; available podium bindings: {names}"
    )


def _load_plan_slices(plan_path: Path) -> list[PlanSlice]:
    raw = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    rows = raw.get("slices") if isinstance(raw, dict) else raw
    if not isinstance(rows, list) or not rows:
        raise PodiumIssuesError(f"{plan_path}: expected non-empty 'slices' list")

    slices: list[PlanSlice] = []
    seen: set[str] = set()
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise PodiumIssuesError(f"{plan_path}: slice {idx} is not an object")
        key = str(row.get("key") or idx)
        if key in seen:
            raise PodiumIssuesError(f"{plan_path}: duplicate slice key {key!r}")
        seen.add(key)
        title = str(row.get("title") or "").strip()
        verification = str(row.get("verification") or "").strip()
        if not title or not verification:
            raise PodiumIssuesError(f"{plan_path}: slice {key!r} needs title+verification")
        acceptance = [str(x) for x in row.get("acceptance", [])]
        if not acceptance:
            raise PodiumIssuesError(f"{plan_path}: slice {key!r} needs acceptance")
        slices.append(
            PlanSlice(
                key=key,
                title=title,
                description=str(row.get("description") or "").strip(),
                acceptance=acceptance,
                verification=verification,
                blocked_by=[str(x) for x in row.get("blocked_by", [])],
                locks=[str(x) for x in row.get("locks", [])],
                priority=row.get("priority"),
            )
        )
    unknown = sorted({b for s in slices for b in s.blocked_by} - seen)
    if unknown:
        raise PodiumIssuesError(f"{plan_path}: unknown blocked_by keys: {unknown}")
    return _dependency_order(slices)


def _dependency_order(slices: list[PlanSlice]) -> list[PlanSlice]:
    remaining = {s.key: s for s in slices}
    emitted: set[str] = set()
    ordered: list[PlanSlice] = []
    while remaining:
        ready = [
            s for s in slices if s.key in remaining and all(b in emitted for b in s.blocked_by)
        ]
        if not ready:
            raise PodiumIssuesError("slice dependency cycle detected")
        for item in ready:
            ordered.append(item)
            emitted.add(item.key)
            remaining.pop(item.key)
    return ordered


def _description(slice_: PlanSlice) -> str:
    acceptance = "\n".join(f"- [ ] {item}" for item in slice_.acceptance)
    return (
        f"## What to build\n\n{slice_.description}\n\n"
        f"## Acceptance criteria\n\n{acceptance}\n\n"
        f"## Verification\n\n{slice_.verification}\n"
    )


def _insert_issue(
    connection: sqlite3.Connection,
    binding: dict[str, Any],
    slice_: PlanSlice,
    blocked_by_ids: list[int],
    now: str,
) -> int:
    approval = binding.get("approval") or {}
    approval_required = (
        bool(approval.get("enabled")) if isinstance(approval, dict) else False
    )
    cursor = connection.execute(
        """
        INSERT INTO issue(
          binding_name, title, description, state, priority, preferred_agent,
          preferred_model, preferred_skill, reasoning_effort, worktree_active,
          approval_required, approved, scheduled_for, base_branch, comments_md,
          context_md, external_id, blocked_by, locks, created_at, updated_at
        ) VALUES (?, ?, ?, 'todo', ?, ?, NULL, NULL, 'high', 0, ?, 0, NULL, ?, '', '', NULL, ?, ?, ?, ?)
        """,
        (
            str(binding["name"]),
            slice_.title,
            _description(slice_),
            slice_.priority,
            binding.get("default_agent"),
            int(approval_required),
            str(binding.get("base_branch") or "main"),
            json.dumps(blocked_by_ids),
            json.dumps(slice_.locks),
            now,
            now,
        ),
    )
    issue_id = cursor.lastrowid
    if issue_id is None:
        raise RuntimeError("insert did not return an issue id")
    return int(issue_id)


def create_plan_issues(
    cwd: Path,
    plan_path: Path,
    *,
    bindings_path: Path = BINDINGS_PATH,
    dry_run: bool = False,
) -> list[str]:
    binding = resolve_binding_for_cwd(cwd, bindings_path)
    slices = _load_plan_slices(plan_path)
    name = str(binding["name"])
    lines = [f"binding={name} slices={len(slices)}"]
    if dry_run:
        for slice_ in slices:
            deps = ",".join(slice_.blocked_by) or "none"
            locks = ",".join(slice_.locks) or "none"
            lines.append(f"{slice_.key} '{slice_.title}' blocked_by={deps} locks={locks} -> podium (dry-run)")
        return lines

    created: dict[str, int] = {}
    now = datetime.now(UTC).isoformat()
    connection = connect()
    try:
        for slice_ in slices:
            blocked_by_ids = [created[key] for key in slice_.blocked_by]
            issue_id = _insert_issue(connection, binding, slice_, blocked_by_ids, now)
            created[slice_.key] = issue_id
            connection.commit()
            lines.append(
                f"{slice_.key} '{slice_.title}' -> podium #{issue_id}"
            )
    finally:
        connection.close()
    return lines


def list_issues(binding_name: str | None = None) -> list[str]:
    connection = connect()
    try:
        if binding_name:
            rows = connection.execute(
                """
                SELECT id, binding_name, title, state, blocked_by, locks
                FROM issue WHERE binding_name = ? ORDER BY id
                """,
                (binding_name,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, binding_name, title, state, blocked_by, locks
                FROM issue ORDER BY id
                """
            ).fetchall()
    finally:
        connection.close()
    lines = []
    for row in rows:
        blocked_by = json.loads(row[4] or "[]")
        locks = json.loads(row[5] or "[]")
        lines.append(
            f"#{row[0]} {row[1]} {row[3]} blocked_by={blocked_by} locks={locks} {row[2]}"
        )
    return lines or ["no issues"]
