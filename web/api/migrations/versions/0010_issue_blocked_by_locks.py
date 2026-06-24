"""add issue dependency and lock columns

Revision ID: 0010_issue_blocked_by_locks
Revises: 0009_issue_external_id
Create Date: 2026-06-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_issue_blocked_by_locks"
down_revision = "0009_issue_external_id"
branch_labels = None
depends_on = None


def _issue_columns() -> set[str]:
    rows = op.get_bind().execute(sa.text("PRAGMA table_info(issue)")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    columns = _issue_columns()
    if "blocked_by" not in columns:
        op.execute("ALTER TABLE issue ADD COLUMN blocked_by TEXT")
    if "locks" not in columns:
        op.execute("ALTER TABLE issue ADD COLUMN locks TEXT")


def downgrade() -> None:
    columns = _issue_columns()
    if "locks" in columns:
        op.execute("ALTER TABLE issue DROP COLUMN locks")
    if "blocked_by" in columns:
        op.execute("ALTER TABLE issue DROP COLUMN blocked_by")
