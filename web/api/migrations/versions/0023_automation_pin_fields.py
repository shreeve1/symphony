"""Automation pin fields (issue #459) + issue origin='automation' CHECK

Revision ID: 0023_automation_pin_fields
Revises: 0022_automation
Create Date: 2026-07-17

Adds the same per-Issue dispatch pin set the New Issue modal exposes
(skill/agent/model/reasoning_effort/base_branch/worktree_active) to the
automation table so a recurring cadence can pin the model and skill without
authoring a throwaway Issue first (Q1 of #459's grill). base_branch falls
back to the binding default at fire-time when unset (Q3).

Automation-spawned Issues carry origin='automation' (Q2) so they're
distinguishable from operator and patrol Issues for future automation-specific
behaviour. SQLite can't ALTER a column-level CHECK in place, so the issue
table is rebuilt with the extended origin CHECK — mirrors the precedent in
0012_retry_verdict. issue_new mirrors SCHEMA_SQL exactly (with 'automation'
appended to the origin CHECK) so the alembic-baseline parity test holds.

Idempotent: skips the issue rebuild if origin already allows 'automation',
skips each ALTER TABLE ADD COLUMN if the column already exists.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0023_automation_pin_fields"
down_revision = "0022_automation"
branch_labels = None
depends_on = None


_ISSUE_COLUMNS = (
    "id, binding_name, title, description, state, priority, preferred_agent, "
    "preferred_model, preferred_skill, reasoning_effort, worktree_active, "
    "base_branch, comments_md, context_md, created_at, updated_at, "
    "latest_run_id, latest_verdict, latest_run_state, last_event_at, "
    "approval_required, approved, scheduled_for, inbox_dismissed_at, "
    "external_id, blocked_by, locks, auto_land, hold, origin, "
    "patrol_incident_family, patrol_incident_resource, "
    "patrol_first_seen_at, patrol_last_seen_at, patrol_occurrence_count, "
    "patrol_current_severity, patrol_last_dispatched_severity, "
    "patrol_pending_severity, patrol_consecutive_passes, patrol_dispatch_count"
)


def _automation_columns() -> set[str]:
    rows = op.get_bind().execute(sa.text("PRAGMA table_info(automation)")).fetchall()
    return {row[1] for row in rows}


def _issue_sql() -> str:
    row = (
        op.get_bind()
        .exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'issue'"
        )
        .fetchone()
    )
    return str(row[0]) if row else ""


def _origin_allows_automation() -> bool:
    return "'automation'" in _issue_sql()


def _add_automation_pin_columns() -> None:
    """Add the six pin columns to automation. Idempotent: skips if present."""
    existing = _automation_columns()
    if "preferred_skill" not in existing:
        op.execute("ALTER TABLE automation ADD COLUMN preferred_skill TEXT")
    if "preferred_agent" not in existing:
        op.execute("ALTER TABLE automation ADD COLUMN preferred_agent TEXT")
    if "preferred_model" not in existing:
        op.execute("ALTER TABLE automation ADD COLUMN preferred_model TEXT")
    if "reasoning_effort" not in existing:
        op.execute(
            "ALTER TABLE automation ADD COLUMN reasoning_effort TEXT DEFAULT 'high'"
        )
    if "base_branch" not in existing:
        op.execute("ALTER TABLE automation ADD COLUMN base_branch TEXT")
    if "worktree_active" not in existing:
        op.execute(
            "ALTER TABLE automation ADD COLUMN worktree_active BOOLEAN DEFAULT FALSE"
        )


def _rebuild_issue_with_automation_origin() -> None:
    """Rebuild issue table so the origin CHECK permits 'automation'.

    SQLite cannot ALTER a column-level CHECK in place, so we recreate the
    table mirroring SCHEMA_SQL exactly (with 'automation' appended to the
    origin CHECK) and copy all rows. Mirrors the 0012_retry_verdict pattern.
    """
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
          origin TEXT NOT NULL DEFAULT 'operator' CHECK (origin IN ('operator','patrol','automation')),
          patrol_incident_family TEXT,
          patrol_incident_resource TEXT,
          patrol_first_seen_at TIMESTAMP,
          patrol_last_seen_at TIMESTAMP,
          patrol_occurrence_count INTEGER NOT NULL DEFAULT 0,
          patrol_current_severity TEXT CHECK (patrol_current_severity IS NULL OR patrol_current_severity IN ('informational','low','medium','high','critical')),
          patrol_last_dispatched_severity TEXT CHECK (patrol_last_dispatched_severity IS NULL OR patrol_last_dispatched_severity IN ('informational','low','medium','high','critical')),
          patrol_pending_severity TEXT CHECK (patrol_pending_severity IS NULL OR patrol_pending_severity IN ('informational','low','medium','high','critical')),
          patrol_consecutive_passes INTEGER NOT NULL DEFAULT 0,
          patrol_dispatch_count INTEGER NOT NULL DEFAULT 0,
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


def upgrade() -> None:
    _add_automation_pin_columns()
    if not _origin_allows_automation():
        _rebuild_issue_with_automation_origin()


def downgrade() -> None:
    # Drop the six pin columns. The CHECK-extension rebuild is NOT
    # reversed: SQLite can't drop a value from a column-level CHECK
    # without another full rebuild, and removing 'automation' from the
    # allowed set would silently invalidate any automation-spawned Issue
    # rows. The asymmetric state (issue table still permits origin=
    # 'automation', automation table has no pin columns) is benign —
    # any automation path would fail trying to read the missing columns,
    # not at the CHECK. Idempotent so `downgrade` does not fail the chain.
    op.execute("ALTER TABLE automation DROP COLUMN worktree_active")
    op.execute("ALTER TABLE automation DROP COLUMN base_branch")
    op.execute("ALTER TABLE automation DROP COLUMN reasoning_effort")
    op.execute("ALTER TABLE automation DROP COLUMN preferred_model")
    op.execute("ALTER TABLE automation DROP COLUMN preferred_agent")
    op.execute("ALTER TABLE automation DROP COLUMN preferred_skill")
