"""Backfill patrol-origin issues to deepseek-v4-flash

Revision ID: 0019_patrol_issues_force_flash
Revises: 0018_run_cache_read_tokens
Create Date: 2026-07-09

Issue #343. Legacy patrol issues created before the create-time flash default
(C-0357) have preferred_model NULL — which falls back to the pi catalog
default (deepseek-v4-pro) at dispatch — and a couple were explicitly pinned to
v4-pro. Patrol issues are long-lived (stable external_id, re-dispatched each
cycle), so the create-time fix never healed them and they kept re-running on
the heavier model. Force every patrol-origin issue onto flash; the create path
now also forces it unconditionally so this cannot re-accrue.

Data-only: no schema change, so the alembic-baseline schema fingerprint is
unaffected.
"""

from __future__ import annotations

from alembic import op


revision = "0019_patrol_issues_force_flash"
down_revision = "0018_run_cache_read_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE issue SET preferred_model = 'deepseek-v4-flash'"
        " WHERE origin = 'patrol'"
        " AND (preferred_model IS NULL OR preferred_model != 'deepseek-v4-flash')"
    )


def downgrade() -> None:
    # Irreversible: the pre-backfill per-issue values (NULL vs pinned v4-pro)
    # are not recoverable. No-op so `downgrade` does not fail the chain.
    pass
