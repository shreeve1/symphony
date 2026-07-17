"""Binding-scoped automations table (ADR-0038 spawn/loop modes)

Revision ID: 0022_automation
Revises: 0021_patrol_incident_history
Create Date: 2026-07-17
"""

from __future__ import annotations

from alembic import op


revision = "0022_automation"
down_revision = "0021_patrol_incident_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation(
          id INTEGER PRIMARY KEY,
          binding_name TEXT NOT NULL REFERENCES binding(name) ON DELETE CASCADE,
          mode TEXT NOT NULL CHECK (mode IN ('spawn','loop')),
          enabled BOOLEAN NOT NULL DEFAULT TRUE,
          template_title TEXT NOT NULL,
          template_body TEXT NOT NULL,
          spawn_interval_seconds INTEGER,
          spawn_run_count INTEGER,
          occurrences_fired INTEGER NOT NULL DEFAULT 0,
          next_fire_at TIMESTAMP,
          loop_iteration_cap INTEGER,
          loop_completion_marker TEXT NOT NULL DEFAULT 'DONE.md',
          created_at TIMESTAMP NOT NULL,
          updated_at TIMESTAMP NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_automation_binding_name ON automation(binding_name)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS automation")
