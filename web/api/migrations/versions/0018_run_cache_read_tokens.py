"""run.cache_read_tokens: cache-read token accounting for RPC usage capture

Revision ID: 0018_run_cache_read_tokens
Revises: 0017_issue_attachments
Create Date: 2026-07-09

Issue #343. pi RPC message_end events carry a usage block (input/output/
cacheRead tokens + a computed cost). Symphony now harvests it into the run
row so patrol token/context spend is measurable. cache_read_tokens is broken
out separately because a large re-fed comment history that is cache-hit is
nearly free, while the same tokens uncached are full price — the split is what
distinguishes cheap re-feed from wasteful re-feed.
"""

from __future__ import annotations

from alembic import op


revision = "0018_run_cache_read_tokens"
down_revision = "0017_issue_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE run ADD COLUMN cache_read_tokens INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE run DROP COLUMN cache_read_tokens")
