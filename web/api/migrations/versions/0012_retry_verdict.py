"""allow retry run verdicts

Revision ID: 0012_retry_verdict
Revises: 0011_issue_auto_land
Create Date: 2026-06-25
"""

from __future__ import annotations

from alembic import op  # type: ignore[import-not-found]

revision = "0012_retry_verdict"
down_revision = "0011_issue_auto_land"
branch_labels = None
depends_on = None

_ISSUE_COLUMNS = (
    "id, binding_name, title, description, state, priority, preferred_agent, "
    "preferred_model, preferred_skill, reasoning_effort, worktree_active, "
    "base_branch, comments_md, context_md, created_at, updated_at, "
    "latest_run_id, latest_verdict, latest_run_state, last_event_at, "
    "approval_required, approved, scheduled_for, inbox_dismissed_at, "
    "external_id, blocked_by, locks, auto_land"
)

_RUN_COLUMNS = (
    "id, issue_id, agent, provider, model, state, verdict, summary, exit_code, "
    "cost_usd, input_tokens, output_tokens, worktree_path, branch_name, "
    "base_branch, log_path, skill_invoked, started_at, ended_at, "
    "agent_session_sha, resumed"
)


def _issue_table_sql() -> str:
    row = (
        op.get_bind()
        .exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'issue'"
        )
        .fetchone()
    )
    return str(row[0]) if row else ""


def _run_table_sql() -> str:
    row = (
        op.get_bind()
        .exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'run'"
        )
        .fetchone()
    )
    return str(row[0]) if row else ""


def _has_retry_verdict() -> bool:
    return "'retry'" in _issue_table_sql() and "'retry'" in _run_table_sql()


def _retry_allowed() -> str:
    return "'done','review','blocked','retry'"


def _retry_disallowed() -> str:
    return "'done','review','blocked'"


def _rebuild(allowed: str) -> None:
    op.execute("PRAGMA foreign_keys = OFF")
    op.execute(
        f"""
        CREATE TABLE issue_new(
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
          latest_verdict TEXT CHECK (latest_verdict IS NULL OR latest_verdict IN ({allowed})),
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
          FOREIGN KEY (latest_run_id) REFERENCES run(id)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE run_new(
          id INTEGER PRIMARY KEY,
          issue_id INTEGER REFERENCES issue(id),
          agent TEXT,
          provider TEXT,
          model TEXT,
          state TEXT NOT NULL CHECK (state IN ('queued','running','succeeded','failed')),
          verdict TEXT CHECK (verdict IS NULL OR verdict IN ({allowed})),
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
          ended_at TIMESTAMP,
          agent_session_sha TEXT,
          resumed BOOLEAN DEFAULT FALSE
        )
        """
    )
    op.execute(f"INSERT INTO issue_new ({_ISSUE_COLUMNS}) SELECT {_ISSUE_COLUMNS} FROM issue")
    op.execute(f"INSERT INTO run_new ({_RUN_COLUMNS}) SELECT {_RUN_COLUMNS} FROM run")
    op.execute("DROP TABLE issue")
    op.execute("DROP TABLE run")
    op.execute("ALTER TABLE issue_new RENAME TO issue")
    op.execute("ALTER TABLE run_new RENAME TO run")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_issue_external_id ON issue(external_id)")
    op.execute("PRAGMA foreign_keys = ON")


def upgrade() -> None:
    if not _has_retry_verdict():
        _rebuild(_retry_allowed())


def downgrade() -> None:
    bind = op.get_bind()
    retry_runs = bind.exec_driver_sql(
        "SELECT COUNT(*) FROM run WHERE verdict = 'retry'"
    ).fetchone()
    if retry_runs and retry_runs[0]:
        raise RuntimeError("Cannot downgrade: run.verdict contains retry")
    retry_issues = bind.exec_driver_sql(
        "SELECT COUNT(*) FROM issue WHERE latest_verdict = 'retry'"
    ).fetchone()
    if retry_issues and retry_issues[0]:
        raise RuntimeError("Cannot downgrade: issue.latest_verdict contains retry")
    if _has_retry_verdict():
        _rebuild(_retry_disallowed())
