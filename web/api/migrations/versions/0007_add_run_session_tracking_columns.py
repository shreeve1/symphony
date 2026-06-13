"""add agent_session_sha and resumed columns to run table

Revision ID: 0007_add_run_session_tracking_columns
Revises: 0006_drop_max_duration_seconds
Create Date: 2026-06-13
"""

from __future__ import annotations

from alembic import op

revision = "0007_add_run_session_tracking_columns"
down_revision = "0006_drop_max_duration_seconds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE run ADD COLUMN agent_session_sha TEXT")
    op.execute("ALTER TABLE run ADD COLUMN resumed BOOLEAN DEFAULT FALSE")


def downgrade() -> None:
    op.execute("ALTER TABLE run DROP COLUMN agent_session_sha")
    op.execute("ALTER TABLE run DROP COLUMN resumed")
