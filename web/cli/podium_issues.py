"""Mirror local kanban issues into Podium as one Issue per file.

`/to-issues` writes vertical-slice issues to ``<repo>/.kanban/issues/{NNN}-{slug}.md``
for the Ralph loop. This module pushes those same issues into Podium so they
dispatch through the Symphony scheduler: each kanban file becomes one Podium
Issue in the binding whose ``repo_path`` matches the current working directory.

DB-direct on purpose: the Podium HTTP API gates ``/api/*`` behind a session
cookie and only the bcrypt password hash lives in the environment, so an
unattended/auto-chained push cannot log in. Inserting through ``web.api.db``
(which honors ``PODIUM_DB_PATH``) hits the same database the running API uses
and mirrors the column list of ``web.api.main.create_binding_issue``.

Issues are inserted in ascending kanban ``id`` order. Podium dispatches todo
issues ``ORDER BY created_at ASC, id ASC`` (``tracker_podium.py``), so insertion
order is the dispatch order — the issues run chronologically. Podium has no
dependency field, so ``blocked_by`` survives only as text inside the issue
description (advisory, not gated).
"""

from __future__ import annotations

import re
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

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)


class PodiumIssuesError(RuntimeError):
    """Raised for operator-facing failures (no binding match, missing board)."""


@dataclass(frozen=True)
class KanbanIssue:
    path: Path
    kid: int
    title: str
    body: str
    podium_issue_id: int | None


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
    """Return the ``tracker: podium`` binding whose repo contains ``cwd``.

    Matches the cwd's git toplevel (falling back to the resolved cwd) against
    each binding's resolved ``repo_path``. Raises ``PodiumIssuesError`` listing
    available podium bindings when nothing matches.
    """
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


def parse_kanban_issue(path: Path) -> KanbanIssue:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise PodiumIssuesError(f"{path}: missing YAML frontmatter")
    front = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).strip("\n")
    if "id" not in front:
        raise PodiumIssuesError(f"{path}: frontmatter missing 'id'")
    # Parse the id from the raw frontmatter token, not the YAML-coerced value:
    # YAML 1.1 reads a zero-padded all-octal-digit id like ``060`` as octal
    # (-> 48). The raw decimal token matches the filename and Ralph's
    # ``grep "^id: NNN$"`` lookup, which both keep the zero-padding.
    id_match = re.search(r"(?m)^id:[ \t]*[\"']?0*([0-9]+)", match.group(1))
    if not id_match:
        raise PodiumIssuesError(f"{path}: frontmatter 'id' is not numeric")
    raw_marker = front.get("podium_issue_id")
    return KanbanIssue(
        path=path,
        kid=int(id_match.group(1), 10),
        title=str(front.get("title") or path.stem),
        body=body,
        podium_issue_id=int(raw_marker) if raw_marker is not None else None,
    )


def scan_pending(kanban_dir: Path) -> list[KanbanIssue]:
    """Parsed issues lacking a ``podium_issue_id`` marker, ascending kanban id."""
    if not kanban_dir.is_dir():
        raise PodiumIssuesError(f"no kanban issues directory at {kanban_dir}")
    issues = [parse_kanban_issue(p) for p in sorted(kanban_dir.glob("*.md"))]
    pending = [i for i in issues if i.podium_issue_id is None]
    return sorted(pending, key=lambda i: i.kid)


def write_back_marker(path: Path, issue_id: int, binding_name: str) -> None:
    """Insert ``podium_issue_id``/``podium_binding`` into the file's frontmatter.

    Body and existing frontmatter keys are preserved verbatim; the two markers
    are appended just before the closing ``---`` fence.
    """
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise PodiumIssuesError(f"{path}: missing YAML frontmatter")
    front_block = match.group(1).rstrip("\n")
    body = text[match.end(1) :]  # includes the trailing "\n---\n..." remainder
    addition = f"\npodium_issue_id: {issue_id}\npodium_binding: {binding_name}"
    path.write_text(f"---\n{front_block}{addition}{body}", encoding="utf-8")


def _insert_issue(
    connection: sqlite3.Connection,
    binding: dict[str, Any],
    issue: KanbanIssue,
    now: str,
) -> int:
    name = str(binding["name"])
    base_branch = str(binding.get("base_branch") or "main")
    preferred_agent = binding.get("default_agent")
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
          context_md, created_at, updated_at
        ) VALUES (?, ?, ?, 'todo', NULL, ?, NULL, NULL, 'high', 0, ?, 0, NULL, ?, '', '', ?, ?)
        """,
        (
            name,
            f"[k#{issue.kid}] {issue.title}",
            issue.body,
            preferred_agent,
            int(approval_required),
            base_branch,
            now,
            now,
        ),
    )
    return int(cursor.lastrowid)


def import_kanban_issues(
    cwd: Path,
    *,
    bindings_path: Path = BINDINGS_PATH,
    dry_run: bool = False,
) -> list[str]:
    """Push pending kanban issues into Podium; yield one summary line per issue.

    Resolves the binding from ``cwd``, scans ``<repo>/.kanban/issues/``, and for
    each file without a ``podium_issue_id`` inserts a Podium Issue (ascending
    kanban id), then writes the marker back. ``dry_run`` performs no DB writes
    and no file mutation.
    """
    binding = resolve_binding_for_cwd(cwd, bindings_path)
    name = str(binding["name"])
    repo_root = Path(str(binding["repo_path"])).resolve()
    pending = scan_pending(repo_root / ".kanban" / "issues")

    lines = [f"binding={name} repo={repo_root} pending={len(pending)}"]
    if not pending:
        lines.append("nothing to import (all issues already have podium_issue_id)")
        return lines
    if dry_run:
        for issue in pending:
            lines.append(f"k#{issue.kid} '{issue.title}' -> podium (dry-run)")
        return lines

    now = datetime.now(UTC).isoformat()
    connection = connect()
    try:
        for issue in pending:
            podium_id = _insert_issue(connection, binding, issue, now)
            connection.commit()
            write_back_marker(issue.path, podium_id, name)
            lines.append(f"k#{issue.kid} '{issue.title}' -> podium #{podium_id}")
    finally:
        connection.close()
    return lines
