from __future__ import annotations

import sqlite3
from collections.abc import Iterable
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


DEFAULT_SOURCE = Path("~/.claude/skills")
MANUAL_SOURCE = ""


def ensure_schema(connection: sqlite3.Connection) -> None:
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
    if has_version_table and connection.execute(
        "SELECT version_num FROM alembic_version"
    ).fetchone():
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


def scan_skills(source: Path = DEFAULT_SOURCE) -> list[SkillRecord]:
    root = source.expanduser().resolve()
    if not root.exists():
        return []

    records: dict[str, SkillRecord] = {}
    for skill_file in sorted(root.rglob("SKILL.md")):
        metadata = _frontmatter(skill_file)
        name = str(metadata.get("name") or skill_file.parent.name).strip()
        if not name:
            continue
        description = str(metadata.get("description") or "").strip()
        records[name] = SkillRecord(
            name=name,
            description=description,
            source=str(skill_file.resolve()),
        )
    return sorted(records.values(), key=lambda skill: skill.name)


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    try:
        end = text.index("\n---", 4)
    except ValueError:
        return {}
    data = yaml.safe_load(text[4:end]) or {}
    return data if isinstance(data, dict) else {}


def refresh_skills(
    source: Path = DEFAULT_SOURCE,
    *,
    dry_run: bool = False,
    connection: sqlite3.Connection | None = None,
) -> list[str]:
    records = scan_skills(source)
    if dry_run:
        return [_format_record(record) for record in records]

    owns_connection = connection is None
    db = connection or connect()
    try:
        ensure_schema(db)
        changes = _apply_refresh(db, records)
        if owns_connection:
            db.commit()
        return changes
    finally:
        if owns_connection:
            db.close()


def _apply_refresh(
    connection: sqlite3.Connection, records: Iterable[SkillRecord]
) -> list[str]:
    desired = {record.name: record for record in records}
    rows = connection.execute(
        "SELECT name, description, source FROM skill ORDER BY name"
    ).fetchall()
    existing = {
        str(row["name"]): SkillRecord(
            name=str(row["name"]),
            description=str(row["description"] or ""),
            source=str(row["source"] or ""),
        )
        for row in rows
    }

    changes: list[str] = []
    for name in sorted(desired):
        record = desired[name]
        old = existing.get(name)
        if old is None:
            changes.append(f"+ {name}")
        elif old != record:
            changes.append(f"~ {name}")
        connection.execute(
            """
            INSERT INTO skill(name, description, source)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
              description = excluded.description,
              source = excluded.source
            """,
            (record.name, record.description, record.source),
        )

    for name in sorted(set(existing) - set(desired)):
        # Empty source means operator-created/manual row; refresh owns only
        # file-backed rows (plus retired legacy seed rows with source='seed').
        if existing[name].source == MANUAL_SOURCE:
            continue
        changes.append(f"- {name}")
        connection.execute("DELETE FROM skill WHERE name = ?", (name,))

    return changes


def _format_record(record: SkillRecord) -> str:
    return f"{record.name}\t{record.description}\t{record.source}"
