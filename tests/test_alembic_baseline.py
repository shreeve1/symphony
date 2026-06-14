from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
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


# The issue table as it existed before 'archived' was added to the state
# CHECK — the shape real live databases were built with and stamped at head,
# which left them unable to accept state='archived' (issue 17).
_PRE_ARCHIVED_ISSUE_SQL = """
CREATE TABLE issue(
  id INTEGER PRIMARY KEY,
  binding_name TEXT REFERENCES binding(name),
  title TEXT,
  description TEXT,
  state TEXT NOT NULL CHECK (state IN ('todo','in_review','running','blocked','done')),
  priority TEXT CHECK (priority IS NULL OR priority IN ('low','med','high','urgent')),
  preferred_agent TEXT,
  preferred_model TEXT,
  preferred_skill TEXT REFERENCES skill(name),
  reasoning_effort TEXT DEFAULT 'high',
  worktree_active BOOLEAN DEFAULT FALSE,
  base_branch TEXT,
  comments_md TEXT DEFAULT '',
  context_md TEXT DEFAULT '',
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  latest_run_id INTEGER,
  latest_verdict TEXT CHECK (latest_verdict IS NULL OR latest_verdict IN ('done','review','blocked')),
  latest_run_state TEXT CHECK (latest_run_state IS NULL OR latest_run_state IN ('queued','running','succeeded','failed')),
  last_event_at TIMESTAMP,
  approval_required BOOLEAN DEFAULT FALSE,
  approved BOOLEAN DEFAULT FALSE,
  scheduled_for TIMESTAMP NULL,
  inbox_dismissed_at TIMESTAMP NULL,
  FOREIGN KEY (latest_run_id) REFERENCES run(id)
);
"""


def test_upgrade_repairs_stale_archived_check(tmp_path: Path, monkeypatch) -> None:
    stale_db = tmp_path / "stale.db"
    monkeypatch.setenv("PODIUM_DB_PATH", str(stale_db))

    # Reproduce a live database: current SCHEMA_SQL except the issue table is
    # the pre-archived shape, stamped one revision behind the new head.
    with sqlite3.connect(stale_db) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.execute("DROP TABLE issue")
        conn.executescript(_PRE_ARCHIVED_ISSUE_SQL)
        conn.execute("CREATE TABLE alembic_version(version_num VARCHAR(32) NOT NULL)")
        conn.execute(
            "INSERT INTO alembic_version(version_num) VALUES "
            "('0007_add_run_session_tracking_columns')"
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO issue (id, state) VALUES (1, 'archived')")

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "web/api/migrations"))
    command.upgrade(config, "head")

    with sqlite3.connect(stale_db) as conn:
        conn.execute("INSERT INTO issue (id, state) VALUES (1, 'archived')")
        conn.commit()
        assert (
            conn.execute("SELECT state FROM issue WHERE id = 1").fetchone()[0]
            == "archived"
        )


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
