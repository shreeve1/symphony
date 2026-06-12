"""drop unused max_duration_seconds column from issue table

Revision ID: 0006_drop_max_duration_seconds
Revises: 0005_inbox_dismissed_at
Create Date: 2026-06-12
"""

from __future__ import annotations

from alembic import op

revision = "0006_drop_max_duration_seconds"
down_revision = "0005_inbox_dismissed_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Host SQLite is >= 3.35, so DROP COLUMN is supported directly. The
    # column was stored but never read by the scheduler; the run timeout is
    # global (config.run_timeout_ms).
    op.execute("ALTER TABLE issue DROP COLUMN max_duration_seconds")


def downgrade() -> None:
    op.execute("ALTER TABLE issue ADD COLUMN max_duration_seconds INTEGER")
