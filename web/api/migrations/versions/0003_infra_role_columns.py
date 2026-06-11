"""add infra role projection columns

Revision ID: 0003_infra_role_columns
Revises: 0002_context_compaction_settings
Create Date: 2026-06-11
"""

from __future__ import annotations

from alembic import op

revision = "0003_infra_role_columns"
down_revision = "0002_context_compaction_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE issue ADD COLUMN approval_required BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE issue ADD COLUMN approved BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE issue ADD COLUMN scheduled_for TIMESTAMP NULL")


def downgrade() -> None:
    with op.batch_alter_table("issue") as batch_op:
        batch_op.drop_column("scheduled_for")
        batch_op.drop_column("approved")
        batch_op.drop_column("approval_required")
