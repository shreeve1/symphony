"""add issue origin provenance column

Revision ID: 0014_issue_origin
Revises: 0013_issue_hold
Create Date: 2026-07-02

Adds an ``origin`` provenance column so the engine can tell operator-created
issues apart from patrol/externally-created ones (ADR-0020 verified-close
scoping). SQLite accepts a column-level CHECK on ``ALTER TABLE ADD COLUMN``,
so the column lands with its two-value CHECK directly (matching the ADD COLUMN
style used by 0011/0013). Existing external rows are backfilled to 'patrol'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_issue_origin"
down_revision = "0013_issue_hold"
branch_labels = None
depends_on = None


def _issue_columns() -> set[str]:
    rows = op.get_bind().execute(sa.text("PRAGMA table_info(issue)")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    if "origin" not in _issue_columns():
        op.execute(
            "ALTER TABLE issue ADD COLUMN origin TEXT NOT NULL DEFAULT 'operator' "
            "CHECK (origin IN ('operator','patrol'))"
        )
        op.execute("UPDATE issue SET origin = 'patrol' WHERE external_id IS NOT NULL")


def downgrade() -> None:
    if "origin" in _issue_columns():
        op.execute("ALTER TABLE issue DROP COLUMN origin")
