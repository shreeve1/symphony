from __future__ import annotations

INITIAL_REVISION = "0025_run_tail_columns"

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
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  source TEXT,
  -- Host the skill was scanned from (ADR-0033). NULL binding_name = host-global
  -- (~/.claude/skills); set = repo-local (that binding's .claude/skills).
  host TEXT,
  binding_name TEXT
);

-- NULL-safe uniqueness: a table-level UNIQUE(name,host,binding_name) does NOT
-- dedupe host-global rows because SQLite treats NULL as distinct, so refresh's
-- ON CONFLICT never fired for binding_name IS NULL and every sync appended a
-- fresh copy. IFNULL(binding_name,'') collapses NULL to a real value so the
-- constraint (and ON CONFLICT) covers host-global rows too.
CREATE UNIQUE INDEX IF NOT EXISTS ux_skill_scope
  ON skill(name, host, IFNULL(binding_name, ''));

CREATE TABLE IF NOT EXISTS issue(
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
  -- Deterministic dedup key (ADR-0015). Nullable: UI-created issues leave it
  -- NULL; SQLite treats NULLs as distinct so many NULL rows coexist under the
  -- global UNIQUE index below.
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
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_issue_external_id ON issue(external_id);

CREATE TABLE IF NOT EXISTS run(
  id INTEGER PRIMARY KEY,
  issue_id INTEGER REFERENCES issue(id),
  agent TEXT,
  provider TEXT,
  model TEXT,
  state TEXT NOT NULL CHECK (state IN ('queued','running','succeeded','failed')),
  verdict TEXT CHECK (verdict IS NULL OR verdict IN ('done','review','blocked','retry')),
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
  resumed BOOLEAN DEFAULT FALSE,
  -- Appended by migration 0018 (issue #343); ALTER ADD COLUMN lands last, so
  -- SCHEMA_SQL must keep it last too for the alembic-baseline fingerprint.
  cache_read_tokens INTEGER,
  agent_session_id TEXT,
  -- B3 live-tail (migration 0025). `agent_session_start_offset` scopes a
  -- local resumed run to its own slice of the shared session JSONL; remote
  -- or fresh runs use 0. `source_id` is `<agent_session_id>:<inode>` at
  -- dispatch so the client can detect file rotation.
  agent_session_start_offset INTEGER,
  source_id TEXT
);

CREATE TABLE IF NOT EXISTS issue_attachment(
  id INTEGER PRIMARY KEY,
  issue_id INTEGER NOT NULL REFERENCES issue(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL,
  stored_name TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  storage_rel_path TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_issue_attachment_issue_id
  ON issue_attachment(issue_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_issue_attachment_issue_stored
  ON issue_attachment(issue_id, stored_name);
CREATE TABLE IF NOT EXISTS automation(
  -- AUTOINCREMENT (not a bare INTEGER PRIMARY KEY): a plain rowid is reused by
  -- SQLite after the row is deleted, and issue.external_id encodes the
  -- automation id ('automation:<id>:<ordinal>'). A reused id whose ordinal
  -- collides with an issue spawned by the deleted automation makes every fire
  -- raise UNIQUE and roll back forever (issue #472). AUTOINCREMENT never reuses
  -- an id, so a recreated automation can never collide with a prior one's issues.
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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
  -- Per-Issue dispatch pins (issue #459). Each nullable; the fire path
  -- (tracker_podium.fire_due_spawn_automations /
  -- reconcile_loop_automations) threads them into insert_issue_row. base_branch
  -- falls back to the binding default at fire-time when NULL.
  preferred_skill TEXT,
  preferred_agent TEXT,
  preferred_model TEXT,
  reasoning_effort TEXT DEFAULT 'high',
  base_branch TEXT,
  worktree_active BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_automation_binding_name ON automation(binding_name);

"""
