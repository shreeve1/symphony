"""add archived issue state

Revision ID: 0004_archived_state
Revises: 0003_infra_role_columns
Create Date: 2026-06-12
"""

from __future__ import annotations

from alembic import op

revision = "0004_archived_state"
down_revision = "0003_infra_role_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite cannot ALTER a CHECK constraint — must rebuild the table.
    op.execute("PRAGMA foreign_keys = OFF")

    op.execute(
        """
        CREATE TABLE issue_new(
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
    op.execute("INSERT INTO issue_new SELECT * FROM issue")
    op.execute("DROP TABLE issue")
    op.execute("ALTER TABLE issue_new RENAME TO issue")

    op.execute("PRAGMA foreign_keys = ON")


def downgrade() -> None:
    # Downgrade requires no archived rows exist — fails loudly otherwise.
    result = op.execute(
        "SELECT COUNT(*) FROM issue WHERE state = 'archived'"
    ).fetchone()
    count = result[0] if result else 0
    if count and count > 0:
        raise RuntimeError(
            f"Cannot downgrade: {count} issue(s) in 'archived' state. "
            "Move or delete them before downgrading."
        )

    op.execute("PRAGMA foreign_keys = OFF")

    op.execute(
        """
        CREATE TABLE issue_old(
          id INTEGER PRIMARY KEY,
          binding_name TEXT REFERENCES binding(name),
          title TEXT,
          description TEXT,
          state TEXT NOT NULL CHECK (state IN ('todo','in_review','running','blocked','done')),
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
    op.execute("INSERT INTO issue_old SELECT * FROM issue")
    op.execute("DROP TABLE issue")
    op.execute("ALTER TABLE issue_old RENAME TO issue")

    op.execute("PRAGMA foreign_keys = ON")
