"""add issue auto_land column

Revision ID: 0011_issue_auto_land
Revises: 0010_issue_blocked_by_locks
Create Date: 2026-06-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_issue_auto_land"
down_revision = "0010_issue_blocked_by_locks"
branch_labels = None
depends_on = None


def _issue_columns() -> set[str]:
    rows = op.get_bind().execute(sa.text("PRAGMA table_info(issue)")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    if "auto_land" not in _issue_columns():
        op.execute("ALTER TABLE issue ADD COLUMN auto_land BOOLEAN NOT NULL DEFAULT FALSE")


def downgrade() -> None:
    if "auto_land" in _issue_columns():
        op.execute("ALTER TABLE issue DROP COLUMN auto_land")
