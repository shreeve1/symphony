"""Backfill patrol-origin issues to pi-duo/Duo

Revision ID: 0020_patrol_issues_force_pi_duo
Revises: 0019_patrol_issues_force_flash
Create Date: 2026-07-16

Issue #413. C-0368 flipped PATROL_DEFAULT_MODEL to the bare provider string
"pi-duo" — which model_catalog.resolve_model() cannot match (the catalog
entry id is "Duo", provider is "pi-duo"). Patrol issues created between
2026-07-14 and now therefore store preferred_model="pi-duo" and are
immediately blocked at the dispatch gate with "model 'pi-duo' is not in
models.yml for agent pi". Fix the constant to "pi-duo/Duo" (companion commit
in web/api/main.py) AND backfill the broken rows so in-flight patrol work
recovers without re-creation.

Data-only: no schema change, so the alembic-baseline schema fingerprint is
unaffected.
"""

from __future__ import annotations

from alembic import op


revision = "0020_patrol_issues_force_pi_duo"
down_revision = "0019_patrol_issues_force_flash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE issue SET preferred_model = 'pi-duo/Duo'"
        " WHERE origin = 'patrol'"
        " AND preferred_model = 'pi-duo'"
    )


def downgrade() -> None:
    # Irreversible: the pre-backfill per-issue values are not recoverable.
    # No-op so `downgrade` does not fail the chain.
    pass
