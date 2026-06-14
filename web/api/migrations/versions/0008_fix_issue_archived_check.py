"""repair issue.state CHECK constraint to include 'archived'

Revision ID: 0008_fix_issue_archived_check
Revises: 0007_add_run_session_tracking_columns
Create Date: 2026-06-14

Databases built from an older SCHEMA_SQL (before 'archived' was added to the
issue.state CHECK) and stamped at head carry a stale CHECK that rejects
``state = 'archived'``. ensure_schema only compares the alembic revision
string, not the actual DDL, so the drift starts the API cleanly but every
attempt to archive an issue fails with a CHECK constraint IntegrityError.
This migration rebuilds the table with the correct CHECK. It is idempotent:
a database whose issue table already lists 'archived' is left untouched.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_fix_issue_archived_check"
down_revision = "0007_add_run_session_tracking_columns"
branch_labels = None
depends_on = None


_ISSUE_COLUMNS = (
    "id, binding_name, title, description, state, priority, preferred_agent, "
    "preferred_model, preferred_skill, reasoning_effort, worktree_active, "
    "base_branch, comments_md, context_md, created_at, updated_at, "
    "latest_run_id, latest_verdict, latest_run_state, last_event_at, "
    "approval_required, approved, scheduled_for, inbox_dismissed_at"
)


def _issue_table_sql() -> str | None:
    row = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'issue'"
            )
        )
        .fetchone()
    )
    return row[0] if row else None


def upgrade() -> None:
    sql = _issue_table_sql() or ""
    if "'archived'" in sql:
        # Already correct (fresh database from current SCHEMA_SQL, or a db that
        # genuinely ran migration 0004). Nothing to repair.
        return

    # SQLite cannot ALTER a CHECK constraint — must rebuild the table. The
    # issue_new definition mirrors SCHEMA_SQL exactly so the post-rebuild
    # schema fingerprint matches a fresh runtime build.
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
          inbox_dismissed_at TIMESTAMP NULL,
          FOREIGN KEY (latest_run_id) REFERENCES run(id)
        )
        """
    )
    op.execute(
        f"INSERT INTO issue_new ({_ISSUE_COLUMNS}) "
        f"SELECT {_ISSUE_COLUMNS} FROM issue"
    )
    op.execute("DROP TABLE issue")
    op.execute("ALTER TABLE issue_new RENAME TO issue")
    op.execute("PRAGMA foreign_keys = ON")


def downgrade() -> None:
    # Reverse the repair only when the table actually carries the archived
    # CHECK and no archived rows remain (they would violate the narrower CHECK).
    sql = _issue_table_sql() or ""
    if "'archived'" not in sql:
        return
    result = (
        op.get_bind()
        .execute(sa.text("SELECT COUNT(*) FROM issue WHERE state = 'archived'"))
        .fetchone()
    )
    count = result[0] if result else 0
    if count:
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
          inbox_dismissed_at TIMESTAMP NULL,
          FOREIGN KEY (latest_run_id) REFERENCES run(id)
        )
        """
    )
    op.execute(
        f"INSERT INTO issue_old ({_ISSUE_COLUMNS}) "
        f"SELECT {_ISSUE_COLUMNS} FROM issue"
    )
    op.execute("DROP TABLE issue")
    op.execute("ALTER TABLE issue_old RENAME TO issue")
    op.execute("PRAGMA foreign_keys = ON")
