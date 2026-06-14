from __future__ import annotations

INITIAL_REVISION = "0008_fix_issue_archived_check"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS binding(
  name TEXT PRIMARY KEY,
  display_name TEXT,
  color TEXT DEFAULT '#888888',
  sort_order INTEGER,
  archived BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS binding_settings(
  binding_name TEXT PRIMARY KEY REFERENCES binding(name) ON DELETE CASCADE,
  context_compact_threshold_tokens INTEGER DEFAULT 16000,
  context_compact_keep_recent_runs INTEGER DEFAULT 3
);

CREATE TABLE IF NOT EXISTS skill(
  name TEXT PRIMARY KEY,
  description TEXT,
  source TEXT
);

CREATE TABLE IF NOT EXISTS issue(
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
  latest_verdict TEXT CHECK (latest_verdict IS NULL OR latest_verdict IN ('done','review','blocked')),
  latest_run_state TEXT CHECK (latest_run_state IS NULL OR latest_run_state IN ('queued','running','succeeded','failed')),
  last_event_at TIMESTAMP,
  approval_required BOOLEAN DEFAULT FALSE,
  approved BOOLEAN DEFAULT FALSE,
  scheduled_for TIMESTAMP NULL,
  inbox_dismissed_at TIMESTAMP NULL,
  FOREIGN KEY (latest_run_id) REFERENCES run(id)
);

CREATE TABLE IF NOT EXISTS run(
  id INTEGER PRIMARY KEY,
  issue_id INTEGER REFERENCES issue(id),
  agent TEXT,
  provider TEXT,
  model TEXT,
  state TEXT NOT NULL CHECK (state IN ('queued','running','succeeded','failed')),
  verdict TEXT CHECK (verdict IS NULL OR verdict IN ('done','review','blocked')),
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
  -- Binding-repo git short-sha at dispatch (NOT the agent session id);
  -- resume eligibility re-feeds on sha drift. See session_continuity.evaluate_resume_eligibility.
  agent_session_sha TEXT,
  resumed BOOLEAN DEFAULT FALSE
);
"""
