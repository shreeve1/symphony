"""per-host/per-binding skill scope + drop issue.preferred_skill FK

Revision ID: 0015_skill_host_binding_scope
Revises: 0014_issue_origin
Create Date: 2026-07-05

ADR-0033. The flat global ``skill`` table (``name PRIMARY KEY``) cannot express
per-host / per-binding skill scoping: the same skill name legitimately exists on
multiple hosts (synced dotfiles) and per repo. This migration rebuilds ``skill``
with a surrogate ``id`` primary key plus ``host``/``binding_name`` columns and a
``UNIQUE(name, host, binding_name)`` constraint. Existing rows are preserved as
host-global rows (``binding_name`` NULL) tagged with the local hostname.

Because ``name`` is no longer unique it can no longer back the
``issue.preferred_skill -> skill(name)`` foreign key, so ``issue`` is rebuilt
without that FK (SQLite cannot drop a constraint in place). Both rebuilds are
idempotent: a fresh database from current SCHEMA_SQL already carries the new
shape and is skipped.
"""

from __future__ import annotations

import socket

import sqlalchemy as sa
from alembic import op

revision = "0015_skill_host_binding_scope"
down_revision = "0014_issue_origin"
branch_labels = None
depends_on = None


def _columns(table: str) -> list[str]:
    rows = op.get_bind().execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return [row[1] for row in rows]


_ISSUE_COLUMNS = (
    "id, binding_name, title, description, state, priority, preferred_agent, "
    "preferred_model, preferred_skill, reasoning_effort, worktree_active, "
    "base_branch, comments_md, context_md, created_at, updated_at, "
    "latest_run_id, latest_verdict, latest_run_state, last_event_at, "
    "approval_required, approved, scheduled_for, inbox_dismissed_at, "
    "external_id, blocked_by, locks, auto_land, hold, origin"
)


def upgrade() -> None:
    _upgrade_skill()
    _upgrade_issue()


def _upgrade_skill() -> None:
    if "host" in _columns("skill"):
        return  # fresh DB from current SCHEMA_SQL
    local_host = socket.gethostname().split(".", 1)[0]
    op.execute("PRAGMA foreign_keys = OFF")
    op.execute(
        """
        CREATE TABLE skill_new(
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          description TEXT,
          source TEXT,
          host TEXT,
          binding_name TEXT,
          UNIQUE(name, host, binding_name)
        )
        """
    )
    # Preserve existing rows as host-global rows on the local host.
    op.execute(
        sa.text(
            "INSERT INTO skill_new(name, description, source, host, binding_name) "
            "SELECT name, description, source, :host, NULL FROM skill"
        ).bindparams(host=local_host)
    )
    op.execute("DROP TABLE skill")
    op.execute("ALTER TABLE skill_new RENAME TO skill")
    op.execute("PRAGMA foreign_keys = ON")


def _upgrade_issue() -> None:
    sql_row = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'issue'"
            )
        )
        .fetchone()
    )
    sql = sql_row[0] if sql_row else ""
    if "REFERENCES skill(name)" not in sql:
        return  # already dropped (fresh DB from current SCHEMA_SQL)

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
          preferred_skill TEXT,
          reasoning_effort TEXT DEFAULT 'high',
          worktree_active BOOLEAN DEFAULT FALSE,
          base_branch TEXT,
          comments_md TEXT DEFAULT '',
          context_md TEXT DEFAULT '',
          created_at TIMESTAMP,
          updated_at TIMESTAMP,
          latest_run_id INTEGER,
          latest_verdict TEXT CHECK (latest_verdict IS NULL OR latest_verdict IN ('done','review','blocked','retry')),
          latest_run_state TEXT CHECK (latest_run_state IS NULL OR latest_run_state IN ('queued','running','succeeded','failed')),
          last_event_at TIMESTAMP,
          approval_required BOOLEAN DEFAULT FALSE,
          approved BOOLEAN DEFAULT FALSE,
          scheduled_for TIMESTAMP NULL,
          inbox_dismissed_at TIMESTAMP NULL,
          external_id TEXT,
          blocked_by TEXT,
          locks TEXT,
          auto_land BOOLEAN NOT NULL DEFAULT FALSE,
          hold BOOLEAN NOT NULL DEFAULT FALSE,
          origin TEXT NOT NULL DEFAULT 'operator' CHECK (origin IN ('operator','patrol')),
          FOREIGN KEY (latest_run_id) REFERENCES run(id)
        )
        """
    )
    op.execute(
        f"INSERT INTO issue_new ({_ISSUE_COLUMNS}) SELECT {_ISSUE_COLUMNS} FROM issue"
    )
    op.execute("DROP TABLE issue")
    op.execute("ALTER TABLE issue_new RENAME TO issue")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_issue_external_id ON issue(external_id)"
    )
    op.execute("PRAGMA foreign_keys = ON")


def downgrade() -> None:
    # Rebuild issue with the FK restored, then collapse skill back to a flat
    # name-keyed table. Skill rows are deduplicated by name (host-global wins).
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
          base_branch TEXT,
          comments_md TEXT DEFAULT '',
          context_md TEXT DEFAULT '',
          created_at TIMESTAMP,
          updated_at TIMESTAMP,
          latest_run_id INTEGER,
          latest_verdict TEXT CHECK (latest_verdict IS NULL OR latest_verdict IN ('done','review','blocked','retry')),
          latest_run_state TEXT CHECK (latest_run_state IS NULL OR latest_run_state IN ('queued','running','succeeded','failed')),
          last_event_at TIMESTAMP,
          approval_required BOOLEAN DEFAULT FALSE,
          approved BOOLEAN DEFAULT FALSE,
          scheduled_for TIMESTAMP NULL,
          inbox_dismissed_at TIMESTAMP NULL,
          external_id TEXT,
          blocked_by TEXT,
          locks TEXT,
          auto_land BOOLEAN NOT NULL DEFAULT FALSE,
          hold BOOLEAN NOT NULL DEFAULT FALSE,
          origin TEXT NOT NULL DEFAULT 'operator' CHECK (origin IN ('operator','patrol')),
          FOREIGN KEY (latest_run_id) REFERENCES run(id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE skill_old(
          name TEXT PRIMARY KEY,
          description TEXT,
          source TEXT
        )
        """
    )
    op.execute(
        "INSERT OR IGNORE INTO skill_old(name, description, source) "
        "SELECT name, description, source FROM skill "
        "ORDER BY (binding_name IS NOT NULL), id"
    )

    op.execute(
        f"INSERT INTO issue_old ({_ISSUE_COLUMNS}) SELECT {_ISSUE_COLUMNS} FROM issue"
    )
    op.execute("DROP TABLE issue")
    op.execute("ALTER TABLE issue_old RENAME TO issue")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_issue_external_id ON issue(external_id)"
    )
    op.execute("DROP TABLE skill")
    op.execute("ALTER TABLE skill_old RENAME TO skill")
    op.execute("PRAGMA foreign_keys = ON")
