# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

# Conventions & Decisions

- Runtime `SCHEMA_SQL` and Alembic head must stay in parity; fresh DBs must stamp `INITIAL_REVISION` to the latest migration head.

# Iteration Log

## #047 Run-row session-tracking columns — 2026-06-13

**What changed:** Added run-table session tracking columns for Session Resume continuity: `agent_session_sha TEXT` and `resumed BOOLEAN DEFAULT FALSE`.
**Files:** `web/api/schema.py`, `web/api/migrations/versions/0007_add_run_session_tracking_columns.py`, `.kanban/issues/047-run-session-tracking-columns.md`.
**Decisions:** Kept scope schema-only; no scheduler, adapter, or prompt changes in this slice. Used SQLite-compatible `BOOLEAN DEFAULT FALSE`, consistent with existing Podium boolean columns.
**Conventions established:** New schema columns require both an Alembic revision and `SCHEMA_SQL` parity, plus `INITIAL_REVISION` bump for fresh DB stamping.
**Notes for next iteration:** #048 and #049 can proceed independently; downstream resume wiring should write `agent_session_sha` and `resumed` into Run rows.
