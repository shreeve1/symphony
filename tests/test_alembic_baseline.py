from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from web.api.schema import SCHEMA_SQL


REPO_ROOT = Path(__file__).resolve().parents[1]


def _schema_fingerprint(connection: sqlite3.Connection) -> dict[str, object]:
    tables = [
        row[0]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_schema
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
              AND name != 'alembic_version'
            ORDER BY name
            """
        )
    ]
    return {
        "tables": tables,
        "columns": {
            table: [tuple(row) for row in connection.execute(f"PRAGMA table_info({table})")]
            for table in tables
        },
        "foreign_keys": {
            table: [tuple(row) for row in connection.execute(f"PRAGMA foreign_key_list({table})")]
            for table in tables
        },
        "indexes": {
            table: [tuple(row) for row in connection.execute(f"PRAGMA index_list({table})")]
            for table in tables
        },
    }


def test_alembic_baseline_matches_runtime_schema(tmp_path: Path, monkeypatch) -> None:
    migrated_db = tmp_path / "migrated.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(migrated_db))

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "web/api/migrations"))
    command.upgrade(config, "head")

    with sqlite3.connect(migrated_db) as migrated:
        migrated_fingerprint = _schema_fingerprint(migrated)

    with sqlite3.connect(":memory:") as runtime:
        runtime.executescript(SCHEMA_SQL)
        runtime_fingerprint = _schema_fingerprint(runtime)

    assert migrated_fingerprint == runtime_fingerprint


def test_alembic_history_is_single_linear_chain() -> None:
    versions = sorted((REPO_ROOT / "web/api/migrations/versions").glob("*.py"))
    revisions: dict[str, str | None] = {}
    for path in versions:
        namespace: dict[str, object] = {}
        exec(path.read_text(encoding="utf-8"), namespace)
        revision = namespace["revision"]
        down_revision = namespace["down_revision"]
        assert isinstance(revision, str)
        assert down_revision is None or isinstance(down_revision, str)
        revisions[revision] = down_revision

    roots = [revision for revision, down_revision in revisions.items() if down_revision is None]
    assert roots == ["0001_initial"]
    assert set(revisions.values()) <= set(revisions) | {None}
    assert len(set(revisions.values()) - {None}) == max(0, len(revisions) - 1)
