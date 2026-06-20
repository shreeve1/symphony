"""add issue.external_id column + global-unique nullable index

Revision ID: 0009_issue_external_id
Revises: 0008_fix_issue_archived_check
Create Date: 2026-06-20

Adds an ``external_id TEXT`` dedup key to the issue table plus a UNIQUE index
``ix_issue_external_id``. The index is intentionally NOT partial: SQLite treats
NULLs as distinct under a UNIQUE constraint, so any number of existing rows /
UI-created issues (external_id IS NULL) coexist while non-null patrol ids stay
globally unique. This mirrors Plane's global ``?external_id=`` lookup contract
(ADR-0015) — the column is global, not composite with binding_name, because the
homelab patrol sha-hash scheme already mints globally collision-proof ids.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_issue_external_id"
down_revision = "0008_fix_issue_archived_check"
branch_labels = None
depends_on = None


def _issue_has_external_id() -> bool:
    rows = (
        op.get_bind()
        .execute(sa.text("PRAGMA table_info(issue)"))
        .fetchall()
    )
    return any(row[1] == "external_id" for row in rows)


def upgrade() -> None:
    # Idempotent, mirroring 0008's check-before-mutate convention. A fresh DB
    # built from current SCHEMA_SQL already carries the column + index but is
    # stamped at the prior revision (ensure_schema stamps INITIAL_REVISION, not
    # head), so a later `alembic upgrade head` must not re-add them.
    if not _issue_has_external_id():
        op.execute("ALTER TABLE issue ADD COLUMN external_id TEXT")
    # Always ensure the index — guard only the ALTER. A column-exists-but-
    # index-missing state (partial prior apply) still needs the index; the
    # IF NOT EXISTS makes the fresh-DB-at-head path a harmless no-op.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_issue_external_id ON issue(external_id)"
    )


def downgrade() -> None:
    if not _issue_has_external_id():
        return
    # Host SQLite is >= 3.35, so DROP COLUMN is supported directly (see
    # 0006_drop_max_duration_seconds). Drop the index first, then the column.
    op.execute("DROP INDEX IF EXISTS ix_issue_external_id")
    op.execute("ALTER TABLE issue DROP COLUMN external_id")
