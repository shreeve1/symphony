"""add agent_session_start_offset and source_id to run table (B3 live-tail)

Revision ID: 0025_run_tail_columns
Revises: 0024_automation_autoincrement_id
Create Date: 2026-07-22

Adds two columns to ``run`` so the live-tail protocol can scope each Run to
its own slice of a shared session JSONL and so rotation is observable to
clients (harness spec §5.2):

  - ``agent_session_start_offset`` (INTEGER): the byte offset in the session
    JSONL where this Run begins. For a local resumed run it is the file size
    at dispatch (so a subsequent tail read scopes within the shared file and
    never leaks prior-run lines); for remote or fresh runs it is 0.
  - ``source_id`` (TEXT): opaque identity of the tail source, computed at
    dispatch as ``<agent_session_id>:<inode>``. A change in ``source_id``
    tells the client the file rotated and the buffer must be reset and
    re-fetched via ``GET /api/runs/{id}/tail``.

Both columns are populated at dispatch (see ``scheduler/run_records.py``);
they are never written by the comments_md prose path.
"""

from __future__ import annotations

from alembic import op


revision = "0025_run_tail_columns"
down_revision = "0024_automation_autoincrement_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE run ADD COLUMN agent_session_start_offset INTEGER")
    op.execute("ALTER TABLE run ADD COLUMN source_id TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE run DROP COLUMN source_id")
    op.execute("ALTER TABLE run DROP COLUMN agent_session_start_offset")
