"""add inbox_dismissed_at column to issue table

Revision ID: 0005_inbox_dismissed_at
Revises: 0004_archived_state
Create Date: 2026-06-12
"""

from __future__ import annotations

from alembic import op

revision = "0005_inbox_dismissed_at"
down_revision = "0004_archived_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE issue ADD COLUMN inbox_dismissed_at TIMESTAMP NULL")


def downgrade() -> None:
    # SQLite does not support DROP COLUMN before 3.35.0. Rebuild the table
    # without the column to support a downgrade.
    op.execute("PRAGMA foreign_keys = OFF")

    op.execute(
        """
        CREATE TABLE issue_old(
          id INTEGER PRIMARY KEY,
          binding_name TEXT REFERENCES binding(name),
          title TEXT,
          description TEXT,
          state TEXT NOT NULL CHECK (state IN ('todo','in_review','running','blocked','done','archived')),
          priority TEXT CHECK (priority IS NULL OR priority IN ('low','med','high','urgent')),
          preferred_agent TEXT,
          preferred_model TEXT,
          preferred_skill TEXT REFERENCES skill(name),
          reasoning_effort TEXT DEFAULT 'high',
          worktree_active BOOLEAN DEFAULT FALSE,
          max_duration_seconds INTEGER,
          base_branch TEXT,
          comments_md TEXT DEFAULT '',
          context_md TEXT DEFAULT '',
          created_at TIMESTAMP,
          updated_at TIMESTAMP,
          latest_run_id INTEGER,
          latest_verdict TEXT CHECK (latest_verdict IS NULL OR latest_verdict IN ('done','review','blocked')),
          latest_run_state TEXT CHECK (latest_run_state IS NULL OR latest_run_state IN ('queued','running','succeeded','failed')),
          last_event_at TIMESTAMP,
          approval_required BOOLEAN DEFAULT FALSE,
          approved BOOLEAN DEFAULT FALSE,
          scheduled_for TIMESTAMP NULL,
          FOREIGN KEY (latest_run_id) REFERENCES run(id)
        )
        """
    )
    op.execute(
        "INSERT INTO issue_old(id, binding_name, title, description, state, priority, "
        "preferred_agent, preferred_model, preferred_skill, reasoning_effort, "
        "worktree_active, max_duration_seconds, base_branch, comments_md, context_md, "
        "created_at, updated_at, latest_run_id, latest_verdict, latest_run_state, "
        "last_event_at, approval_required, approved, scheduled_for) "
        "SELECT id, binding_name, title, description, state, priority, "
        "preferred_agent, preferred_model, preferred_skill, reasoning_effort, "
        "worktree_active, max_duration_seconds, base_branch, comments_md, context_md, "
        "created_at, updated_at, latest_run_id, latest_verdict, latest_run_state, "
        "last_event_at, approval_required, approved, scheduled_for FROM issue"
    )
    op.execute("DROP TABLE issue")
    op.execute("ALTER TABLE issue_old RENAME TO issue")

    op.execute("PRAGMA foreign_keys = ON")
