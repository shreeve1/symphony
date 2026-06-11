"""add context compaction settings

Revision ID: 0002_context_compaction_settings
Revises: 0001_initial
Create Date: 2026-06-11
"""

from __future__ import annotations

from alembic import op

revision = "0002_context_compaction_settings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE binding_settings(
          binding_name TEXT PRIMARY KEY REFERENCES binding(name) ON DELETE CASCADE,
          context_compact_threshold_tokens INTEGER DEFAULT 16000,
          context_compact_keep_recent_runs INTEGER DEFAULT 3
        )
        """
    )


def downgrade() -> None:
    op.drop_table("binding_settings")
