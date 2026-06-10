"""initial Podium schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-10
"""

from __future__ import annotations

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE binding(
          name TEXT PRIMARY KEY,
          display_name TEXT,
          color TEXT DEFAULT '#888888',
          sort_order INTEGER,
          archived BOOLEAN DEFAULT FALSE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE skill(
          name TEXT PRIMARY KEY,
          description TEXT,
          source TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE issue(
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
          FOREIGN KEY (latest_run_id) REFERENCES run(id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE run(
          id INTEGER PRIMARY KEY,
          issue_id INTEGER REFERENCES issue(id),
          agent TEXT,
          provider TEXT,
          model TEXT,
          state TEXT NOT NULL CHECK (state IN ('queued','running','succeeded','failed')),
          verdict TEXT CHECK (verdict IS NULL OR verdict IN ('done','review','blocked')),
          summary TEXT,
          exit_code INTEGER,
          cost_usd NUMERIC,
          input_tokens INTEGER,
          output_tokens INTEGER,
          worktree_path TEXT,
          branch_name TEXT,
          base_branch TEXT,
          log_path TEXT,
          skill_invoked TEXT,
          started_at TIMESTAMP,
          ended_at TIMESTAMP
        )
        """
    )


def downgrade() -> None:
    op.drop_table("run")
    op.drop_table("issue")
    op.drop_table("skill")
    op.drop_table("binding")
