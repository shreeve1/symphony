from __future__ import annotations

import logging
import socket
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import yaml

_db = cast(Any, import_module("web.api.db"))
_schema = cast(Any, import_module("web.api.schema"))
connect = _db.connect
INITIAL_REVISION = _schema.INITIAL_REVISION
SCHEMA_SQL = _schema.SCHEMA_SQL

logger = logging.getLogger(__name__)

# ~ expands on the *target* host, so the same literal works for local and SSH
# scans. binding_name NULL rows come from this host-global directory (ADR-0033).
GLOBAL_SUBPATH = ".claude/skills"
PROJECT_SUBPATH = ".claude/skills"
MANUAL_SOURCE = ""

# Backwards-compatible constants for the manual CLI path.
DEFAULT_SOURCE = Path("~/.claude/skills")
PROJECT_SOURCE = Path(".claude/skills")


def ensure_schema(connection) -> None:
    """Build a fresh Podium schema; leave existing databases untouched.

    Mirrors `web.api.main.ensure_schema`'s never-re-stamp contract: running
    SCHEMA_SQL against an old database would create newly-shipped tables at
    head shape outside migrations, so an existing database (any
    alembic_version row) is left for `alembic upgrade head`.
    """
    has_version_table = connection.execute(
        "SELECT name FROM sqlite_schema WHERE type = 'table'"
        " AND name = 'alembic_version'"
    ).fetchone()
    if (
        has_version_table
        and connection.execute("SELECT version_num FROM alembic_version").fetchone()
    ):
        return
    connection.executescript(SCHEMA_SQL)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS alembic_version(version_num VARCHAR(32) NOT NULL)"
    )
    connection.execute(
        "INSERT INTO alembic_version(version_num) VALUES (?)", (INITIAL_REVISION,)
    )
    connection.commit()


@dataclass(frozen=True, order=True)
class SkillRecord:
    name: str
    description: str
    source: str
    host: str | None = None
    binding_name: str | None = None


def _parse_frontmatter(text: str) -> dict[str, object]:
    if not text.startswith("---\n"):
        return {}
    try:
        end = text.index("\n---", 4)
    except ValueError:
        return {}
    data = yaml.safe_load(text[4:end]) or {}
    return data if isinstance(data, dict) else {}


def _record_from_frontmatter(
    text: str, *, fallback_name: str, source: str, host: str | None, binding: str | None
) -> SkillRecord | None:
    metadata = _parse_frontmatter(text)
    name = str(metadata.get("name") or fallback_name).strip()
    if not name:
        return None
    description = str(metadata.get("description") or "").strip()
    return SkillRecord(
        name=name,
        description=description,
        source=source,
        host=host,
        binding_name=binding,
    )


def scan_skills(source: Path = DEFAULT_SOURCE) -> list[SkillRecord]:
    """Scan a local directory tree for SKILL.md files (host/binding unset)."""
    root = source.expanduser().resolve()
    if not root.exists():
        return []
    records: dict[str, SkillRecord] = {}
    for skill_file in sorted(root.rglob("SKILL.md")):
        record = _record_from_frontmatter(
            skill_file.read_text(encoding="utf-8"),
            fallback_name=skill_file.parent.name,
            source=str(skill_file.resolve()),
            host=None,
            binding=None,
        )
        if record is not None:
            records[record.name] = record
    return sorted(records.values(), key=lambda skill: skill.name)


def _scan_local_scope(
    directory: str, *, host: str, binding: str | None
) -> list[SkillRecord]:
    root = Path(directory).expanduser()
    if not root.exists():
        return []
    records: dict[str, SkillRecord] = {}
    for skill_file in sorted(root.rglob("SKILL.md")):
        record = _record_from_frontmatter(
            skill_file.read_text(encoding="utf-8"),
            fallback_name=skill_file.parent.name,
            source=str(skill_file),
            host=host,
            binding=binding,
        )
        if record is not None:
            records[record.name] = record
    return sorted(records.values(), key=lambda skill: skill.name)


# Marker the remote shell emits between concatenated SKILL.md files so the
# scanner can split one SSH round-trip back into per-file blocks.
_REMOTE_FILE_MARKER = "@@@SYMPHONY_SKILL_FILE@@@"
_REMOTE_SCAN_SCRIPT = (
    'd="{directory}"; d="${{d/#\\~/$HOME}}"; '
    '[ -d "$d" ] || exit 0; '
    # -L follows symlinks: ~/.claude/skills is commonly a dotfiles symlink, and
    # find without -L will not descend a symlinked root (mirrors Python rglob,
    # which does follow it, so local and remote scans stay consistent).
    'find -L "$d" -name SKILL.md 2>/dev/null | sort | while read -r f; do '
    f'echo "{_REMOTE_FILE_MARKER} $f"; cat "$f"; done'
)


def _scan_remote_scope(
    remote,
    directory: str,
    *,
    host: str,
    binding: str | None,
    ssh_run: Callable[..., Any],
) -> list[SkillRecord]:
    import ssh_support

    script = _REMOTE_SCAN_SCRIPT.format(directory=directory)
    args = [*ssh_support.ssh_base_args(remote), script]
    result = ssh_run(args, capture_output=True, text=True, timeout=30, check=False)
    if getattr(result, "returncode", 1) != 0:
        raise RuntimeError(
            f"remote scan exit {getattr(result, 'returncode', '?')}: "
            f"{getattr(result, 'stderr', '') or ''}".strip()
        )
    return _parse_remote_blocks(result.stdout or "", host=host, binding=binding)


def _parse_remote_blocks(
    stdout: str, *, host: str, binding: str | None
) -> list[SkillRecord]:
    records: dict[str, SkillRecord] = {}
    blocks = stdout.split(_REMOTE_FILE_MARKER)
    for block in blocks[1:]:  # blocks[0] precedes the first marker
        newline = block.find("\n")
        if newline == -1:
            continue
        path = block[:newline].strip()
        body = block[newline + 1 :]
        fallback = Path(path).parent.name if path else ""
        record = _record_from_frontmatter(
            body, fallback_name=fallback, source=path, host=host, binding=binding
        )
        if record is not None:
            records[record.name] = record
    return sorted(records.values(), key=lambda skill: skill.name)


def _remote_policy(binding: dict[str, Any]):
    remote = binding.get("remote")
    if not isinstance(remote, dict):
        return None
    from config import RemotePolicy

    return RemotePolicy(
        host=str(remote.get("host") or ""),
        user=str(remote.get("user") or ""),
        identity=remote.get("identity"),
    )


def _host_label(host: str) -> str:
    return host.split(".", 1)[0]


def sync_skills(
    bindings: Iterable[dict[str, Any]],
    *,
    connection=None,
    dry_run: bool = False,
    local_hostname: str | None = None,
    ssh_run: Callable[..., Any] = subprocess.run,
) -> list[str]:
    """Scan every binding's host and repo, upsert per (host, binding) scope.

    Host-global skills (``~/.claude/skills`` on each host) land with
    ``binding_name`` NULL; a binding's repo ``.claude/skills`` land scoped to
    that binding. Local host is scanned directly; remote bindings over SSH.
    Best-effort: an unreachable host leaves its existing rows intact and is
    logged, never raising (ADR-0033).
    """
    local_host = _host_label(local_hostname or socket.gethostname())
    bindings = list(bindings)

    # Group scans by host so each host's global directory is scanned once.
    scanned_scopes: dict[tuple[str, str | None], list[SkillRecord]] = {}
    scanned_hosts: set[str] = set()

    def scan_host_global(host: str, remote) -> None:
        if host in scanned_hosts:
            return
        scanned_hosts.add(host)
        try:
            if remote is None:
                records = _scan_local_scope(
                    str(Path("~") / GLOBAL_SUBPATH), host=host, binding=None
                )
            else:
                records = _scan_remote_scope(
                    remote,
                    f"~/{GLOBAL_SUBPATH}",
                    host=host,
                    binding=None,
                    ssh_run=ssh_run,
                )
        except Exception as exc:  # noqa: BLE001 - best-effort per host
            logger.warning("skill_sync_host_global_failed host=%s error=%s", host, exc)
            return
        scanned_scopes[(host, None)] = records

    for binding in bindings:
        name = str(binding.get("name") or "").strip()
        repo_path = binding.get("repo_path")
        if not name or not repo_path:
            continue
        remote = _remote_policy(binding)
        host = _host_label(remote.host) if remote and remote.host else local_host

        scan_host_global(host, remote)

        project_dir = f"{str(repo_path).rstrip('/')}/{PROJECT_SUBPATH}"
        try:
            if remote is None:
                records = _scan_local_scope(project_dir, host=host, binding=name)
            else:
                records = _scan_remote_scope(
                    remote, project_dir, host=host, binding=name, ssh_run=ssh_run
                )
        except Exception as exc:  # noqa: BLE001 - best-effort per binding
            logger.warning(
                "skill_sync_project_failed binding=%s host=%s error=%s",
                name,
                host,
                exc,
            )
            continue
        scanned_scopes[(host, name)] = records

    all_records = [r for records in scanned_scopes.values() for r in records]
    if dry_run:
        return [_format_record(r) for r in sorted(all_records)]

    owns_connection = connection is None
    db = connection or connect()
    try:
        ensure_schema(db)
        changes = _apply_sync(db, scanned_scopes)
        if owns_connection:
            db.commit()
        return changes
    finally:
        if owns_connection:
            db.close()


def _apply_sync(
    connection, scanned_scopes: dict[tuple[str, str | None], list[SkillRecord]]
) -> list[str]:
    """Replace rows within each successfully-scanned (host, binding) scope.

    Scopes that were not scanned (unreachable host) are untouched. Manual rows
    (``source = ''``) are never deleted.
    """
    changes: list[str] = []
    for (host, binding), records in scanned_scopes.items():
        existing = {
            str(row["name"]): row["source"]
            for row in connection.execute(
                "SELECT name, source FROM skill WHERE host IS ? AND binding_name IS ?",
                (host, binding),
            ).fetchall()
        }
        desired = {r.name for r in records}

        for record in sorted(records):
            if record.name not in existing:
                changes.append(f"+ {_scope_label(host, binding)} {record.name}")
            connection.execute(
                """
                INSERT INTO skill(name, description, source, host, binding_name)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name, host, binding_name) DO UPDATE SET
                  description = excluded.description,
                  source = excluded.source
                """,
                (record.name, record.description, record.source, host, binding),
            )

        for name in sorted(set(existing) - desired):
            if existing[name] == MANUAL_SOURCE:
                continue
            changes.append(f"- {_scope_label(host, binding)} {name}")
            connection.execute(
                "DELETE FROM skill WHERE name = ? AND host IS ? AND binding_name IS ?",
                (name, host, binding),
            )
    return changes


def _scope_label(host: str, binding: str | None) -> str:
    return f"[{host}/{binding or 'global'}]"


def _format_record(record: SkillRecord) -> str:
    scope = _scope_label(record.host or "?", record.binding_name)
    return f"{scope}\t{record.name}\t{record.description}\t{record.source}"
