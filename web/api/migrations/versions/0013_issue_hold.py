"""add issue hold column

Revision ID: 0013_issue_hold
Revises: 0012_retry_verdict
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_issue_hold"
down_revision = "0012_retry_verdict"
branch_labels = None
depends_on = None


def _issue_columns() -> set[str]:
    rows = op.get_bind().execute(sa.text("PRAGMA table_info(issue)")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    if "hold" not in _issue_columns():
        op.execute("ALTER TABLE issue ADD COLUMN hold BOOLEAN NOT NULL DEFAULT FALSE")


def downgrade() -> None:
    if "hold" in _issue_columns():
        op.execute("ALTER TABLE issue DROP COLUMN hold")
