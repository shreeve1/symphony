"""issue_attachment: checkout-local attachment metadata

Revision ID: 0017_issue_attachments
Revises: 0016_skill_scope_null_safe_unique
Create Date: 2026-07-08

ADR-0035. Adds the issue_attachment table, issue_id index, and unique
composite index on (issue_id, stored_name). ON DELETE CASCADE from issue_id
ensures archived issue purge cleans metadata without a separate sweep.
"""

from __future__ import annotations

from alembic import op


revision = "0017_issue_attachments"
down_revision = "0016_skill_scope_null_safe_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS issue_attachment(
          id INTEGER PRIMARY KEY,
          issue_id INTEGER NOT NULL REFERENCES issue(id) ON DELETE CASCADE,
          display_name TEXT NOT NULL,
          stored_name TEXT NOT NULL,
          content_type TEXT NOT NULL,
          size_bytes INTEGER NOT NULL,
          storage_rel_path TEXT NOT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_issue_attachment_issue_id"
        " ON issue_attachment(issue_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_issue_attachment_issue_stored"
        " ON issue_attachment(issue_id, stored_name)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS issue_attachment")
