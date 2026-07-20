"""ensure_schema contract: fresh stamp only, never re-stamp, drift detection.

Regression for the 2026-06-12 stamp-vs-run drift: the old implementation
UPDATEd alembic_version to the code's INITIAL_REVISION on every boot, so a
restart after a schema-bumping commit recorded a migration that never ran.
"""

from __future__ import annotations

import sqlite3

import pytest

from web.api.main import INITIAL_REVISION, ensure_schema
from web.api.schema import SCHEMA_SQL


ALEMBIC_HEAD = "0024_automation_autoincrement_id"


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    return connection


def _revision(connection: sqlite3.Connection) -> str:
    return str(
        connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    )


def test_fresh_database_gets_schema_and_head_stamp() -> None:
    connection = _connect()
    ensure_schema(connection)
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'table'"
        )
    }
    assert "issue" in tables and "run" in tables
    assert _revision(connection) == ALEMBIC_HEAD


def test_existing_database_at_head_does_not_warn_about_revision(caplog) -> None:
    connection = _connect()
    connection.executescript(SCHEMA_SQL)
    connection.execute("CREATE TABLE alembic_version(version_num VARCHAR(32) NOT NULL)")
    connection.execute(
        "INSERT INTO alembic_version(version_num) VALUES (?)", (ALEMBIC_HEAD,)
    )
    connection.commit()

    ensure_schema(connection)

    assert "podium_schema_revision_mismatch" not in caplog.text


def test_existing_database_is_never_restamped() -> None:
    connection = _connect()
    connection.executescript(SCHEMA_SQL)
    connection.execute("CREATE TABLE alembic_version(version_num VARCHAR(32) NOT NULL)")
    connection.execute(
        "INSERT INTO alembic_version(version_num) VALUES ('0005_inbox_dismissed_at')"
    )
    connection.commit()

    ensure_schema(connection)

    assert _revision(connection) == "0005_inbox_dismissed_at"


def test_missing_column_fails_startup_loudly() -> None:
    connection = _connect()
    connection.executescript(SCHEMA_SQL)
    connection.execute("CREATE TABLE alembic_version(version_num VARCHAR(32) NOT NULL)")
    connection.execute(
        "INSERT INTO alembic_version(version_num) VALUES ('0005_inbox_dismissed_at')"
    )
    connection.execute("ALTER TABLE issue DROP COLUMN inbox_dismissed_at")
    connection.commit()

    with pytest.raises(RuntimeError, match="issue.inbox_dismissed_at"):
        ensure_schema(connection)


def test_extra_column_only_warns() -> None:
    connection = _connect()
    connection.executescript(SCHEMA_SQL)
    connection.execute("CREATE TABLE alembic_version(version_num VARCHAR(32) NOT NULL)")
    connection.execute(
        f"INSERT INTO alembic_version(version_num) VALUES ('{INITIAL_REVISION}')"
    )
    connection.execute("ALTER TABLE issue ADD COLUMN legacy_extra INTEGER")
    connection.commit()

    ensure_schema(connection)  # must not raise

    assert _revision(connection) == INITIAL_REVISION
