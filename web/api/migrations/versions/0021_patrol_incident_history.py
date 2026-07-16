"""Patrol incident persistence: family/resource, severity, dispatch count, session id

Revision ID: 0021_patrol_incident_history
Revises: 0020_patrol_issues_force_pi_duo
Create Date: 2026-07-16

Adds nullable/defaulted patrol Incident columns to issue plus agent_session_id
to run. Backfills patrol_dispatch_count from the persisted Run count before any
pruning, and leaves NULL agent_session_id for existing runs (runtime handles
null fallback). Identity is NOT recovered from patrol-status markers because
those markers don't carry the incident fields (family/resource) — see inline
ponytail comment.
"""

from __future__ import annotations

from alembic import op


revision = "0021_patrol_incident_history"
down_revision = "0020_patrol_issues_force_pi_duo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── issue columns ─────────────────────────────────────────────
    op.execute("ALTER TABLE issue ADD COLUMN patrol_incident_family TEXT")
    op.execute("ALTER TABLE issue ADD COLUMN patrol_incident_resource TEXT")
    op.execute("ALTER TABLE issue ADD COLUMN patrol_first_seen_at TIMESTAMP")
    op.execute("ALTER TABLE issue ADD COLUMN patrol_last_seen_at TIMESTAMP")
    op.execute(
        "ALTER TABLE issue ADD COLUMN patrol_occurrence_count"
        " INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE issue ADD COLUMN patrol_current_severity TEXT"
        " CHECK (patrol_current_severity IS NULL"
        " OR patrol_current_severity IN"
        " ('informational','low','medium','high','critical'))"
    )
    op.execute(
        "ALTER TABLE issue ADD COLUMN patrol_last_dispatched_severity TEXT"
        " CHECK (patrol_last_dispatched_severity IS NULL"
        " OR patrol_last_dispatched_severity IN"
        " ('informational','low','medium','high','critical'))"
    )
    op.execute(
        "ALTER TABLE issue ADD COLUMN patrol_pending_severity TEXT"
        " CHECK (patrol_pending_severity IS NULL"
        " OR patrol_pending_severity IN"
        " ('informational','low','medium','high','critical'))"
    )
    op.execute(
        "ALTER TABLE issue ADD COLUMN patrol_consecutive_passes"
        " INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE issue ADD COLUMN patrol_dispatch_count INTEGER NOT NULL DEFAULT 0"
    )

    # ── run column ────────────────────────────────────────────────
    op.execute("ALTER TABLE run ADD COLUMN agent_session_id TEXT")

    # ── Backfill: patrol_dispatch_count from existing Run rows ────
    op.execute(
        "UPDATE issue SET patrol_dispatch_count = ("
        "  SELECT COUNT(*) FROM run WHERE run.issue_id = issue.id"
        ") WHERE origin = 'patrol'"
    )

    # ── Backfill: patrol identity from patrol-status markers ──────
    # The patrol-status marker (<!-- patrol-status: {...} -->) in
    # issue.description does NOT carry incident_family or
    # incident_resource (those are new fields introduced by this
    # feature). We leave family/resource NULL for all existing rows,
    # preserving exact external_id separation so no historical
    # duplicates are silently merged. The observe endpoint will only
    # adopt an existing row if its external_id appears in the caller's
    # legacy_external_ids list.
    #
    # ponytail: markers don't carry these fields, skip parsing.

    # ── Backfill: Run agent_session_id ────────────────────────────
    # Run agent_session_id is left NULL for existing runs — the
    # runtime falls back to derive_session_id(issue_id) when
    # agent_session_id IS NULL (see _SessionTailer: "retain
    # derive_session_id(issue_id) only as a legacy null fallback").
    # NULL is the explicit legacy marker, no backfill needed.
    # ponytail: runtime handles NULL, skip backfill.


def downgrade() -> None:
    # Reverse both ADD COLUMN batches. SQLite >= 3.35 supports
    # ALTER TABLE DROP COLUMN (verified: host runs 3.45). DROP in
    # reverse ADD order so SQLite's column-ordering bookkeeping is
    # clean. The project uses this same pattern in 0006/0007/0009.
    op.execute("ALTER TABLE run DROP COLUMN agent_session_id")
    op.execute("ALTER TABLE issue DROP COLUMN patrol_dispatch_count")
    op.execute("ALTER TABLE issue DROP COLUMN patrol_consecutive_passes")
    op.execute("ALTER TABLE issue DROP COLUMN patrol_pending_severity")
    op.execute("ALTER TABLE issue DROP COLUMN patrol_last_dispatched_severity")
    op.execute("ALTER TABLE issue DROP COLUMN patrol_current_severity")
    op.execute("ALTER TABLE issue DROP COLUMN patrol_occurrence_count")
    op.execute("ALTER TABLE issue DROP COLUMN patrol_last_seen_at")
    op.execute("ALTER TABLE issue DROP COLUMN patrol_first_seen_at")
    op.execute("ALTER TABLE issue DROP COLUMN patrol_incident_resource")
    op.execute("ALTER TABLE issue DROP COLUMN patrol_incident_family")
