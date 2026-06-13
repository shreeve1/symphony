---
id: 047
title: Run-row session-tracking columns
status: review
blocked_by: []
parent: null
priority: 0
created: 2026-06-13
---

## What to build

Add two columns to the `run` table to support Session Resume continuity:

- `agent_session_sha` (TEXT, nullable) — git HEAD captured at run start. Compared at the next dispatch to detect a git rug-pull (HEAD moved under the session since it last ran).
- `resumed` (INTEGER/BOOL, default 0) — whether this run resumed an existing agent session vs started fresh. Observability only; no engine logic branches on it.

Ship both via an Alembic migration AND the runtime `SCHEMA_SQL`, keeping migration/runtime schema parity (this repo enforces parity — see migration `0002` / #023b / #026). `ensure_schema(...)` must stamp the new runtime revision for schema-created DBs, and the boot schema-drift check must accept the new columns.

No adapter, scheduler, or prompt changes here — this is the schema foundation only.

## Acceptance criteria

- [ ] `run` table has `agent_session_sha` (nullable TEXT) and `resumed` (default false) in both `web/api/schema.py` `SCHEMA_SQL` and a new Alembic migration revision.
- [ ] Alembic head and runtime `SCHEMA_SQL` produce identical `run` table PRAGMA (parity test passes).
- [ ] `ensure_schema(...)` updates `alembic_version` to the new revision for schema-created DBs.
- [ ] Existing rows/migrations upgrade cleanly (nullable + default, no backfill required).
- [ ] A test asserts both columns are present and default correctly on a fresh DB.

## Verification

`uv run pytest tests/test_alembic_baseline.py tests/test_run_reconcile.py -q`

## Blocked by

None — can start immediately.
