"""null-safe skill scope uniqueness; dedupe accumulated host-global rows

Revision ID: 0016_skill_scope_null_safe_unique
Revises: 0015_skill_host_binding_scope
Create Date: 2026-07-06

ADR-0033 follow-up. 0015 used a table-level UNIQUE(name, host, binding_name),
but SQLite treats NULL as distinct under UNIQUE, so host-global rows
(binding_name IS NULL) never triggered the sync's ON CONFLICT — every skill
refresh appended a fresh duplicate copy of every host-global skill, so the
catalog grew without bound across restarts.

Fix: replace the table-level UNIQUE with a unique expression index on
(name, host, IFNULL(binding_name, '')), which collapses NULL to a real value so
uniqueness (and ON CONFLICT) covers host-global rows too. Existing duplicate
rows are collapsed to the lowest id per (name, host, IFNULL(binding_name,''))
scope first, or the unique index creation would fail.

Idempotent: a fresh database from current SCHEMA_SQL already has the expression
index and no table-level UNIQUE, so it is left untouched.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_skill_scope_null_safe_unique"
down_revision = "0015_skill_host_binding_scope"
branch_labels = None
depends_on = None


def _skill_table_has_unique() -> bool:
    row = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'skill'"
            )
        )
        .fetchone()
    )
    # Whitespace-insensitive: SQLite echoes the DDL verbatim, so SCHEMA_SQL's
    # spaced form and a hand-written unspaced form both resolve.
    sql = (row[0] if row else "").replace(" ", "").upper()
    return "UNIQUE(NAME,HOST,BINDING_NAME)" in sql


def upgrade() -> None:
    if not _skill_table_has_unique():
        # Fresh DB already at target shape (table-level UNIQUE absent). Ensure
        # the expression index exists (harmless no-op when already present).
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_skill_scope"
            " ON skill(name, host, IFNULL(binding_name, ''))"
        )
        return

    # Collapse duplicate rows to the lowest id per null-safe scope before the
    # unique index can be built.
    op.execute(
        """
        DELETE FROM skill
        WHERE id NOT IN (
          SELECT MIN(id) FROM skill
          GROUP BY name, host, IFNULL(binding_name, '')
        )
        """
    )

    op.execute("PRAGMA foreign_keys = OFF")
    op.execute(
        """
        CREATE TABLE skill_new(
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          description TEXT,
          source TEXT,
          host TEXT,
          binding_name TEXT
        )
        """
    )
    op.execute(
        "INSERT INTO skill_new(id, name, description, source, host, binding_name) "
        "SELECT id, name, description, source, host, binding_name FROM skill"
    )
    op.execute("DROP TABLE skill")
    op.execute("ALTER TABLE skill_new RENAME TO skill")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_skill_scope"
        " ON skill(name, host, IFNULL(binding_name, ''))"
    )
    op.execute("PRAGMA foreign_keys = ON")


def downgrade() -> None:
    if _skill_table_has_unique():
        return  # already table-level UNIQUE

    op.execute("PRAGMA foreign_keys = OFF")
    op.execute("DROP INDEX IF EXISTS ux_skill_scope")
    op.execute(
        """
        CREATE TABLE skill_old(
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          description TEXT,
          source TEXT,
          host TEXT,
          binding_name TEXT,
          UNIQUE(name, host, binding_name)
        )
        """
    )
    op.execute(
        "INSERT INTO skill_old(id, name, description, source, host, binding_name) "
        "SELECT id, name, description, source, host, binding_name FROM skill"
    )
    op.execute("DROP TABLE skill")
    op.execute("ALTER TABLE skill_old RENAME TO skill")
    op.execute("PRAGMA foreign_keys = ON")
