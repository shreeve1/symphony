---
title: Podium #023b — Alembic baseline and SQLite backup wiring
type: analysis
status: promoted
created: 2026-06-11
updated: 2026-06-11
sources:
  - tests/test_alembic_baseline.py
  - web/api/migrations/env.py
  - web/api/migrations/README.md
  - scripts/podium-backup.sh
  - wiki/raw/podium-backup.cron
  - web/README.md
  - wiki/raw/sessions/2026-06-11-podium-023b-alembic-backup.md
confidence: high
tags: [podium, alembic, sqlite, backup, cron, pytest]
---

# Podium #023b — Alembic baseline and SQLite backup wiring

## Summary

#023b landed two operational hardenings: an Alembic baseline test that keeps migrations aligned with the runtime SQLite schema, and a host cron backup path for the active Podium database plus run logs. Verification passed with `uv run pytest` and a live backup file under `/backup`. [source: tests/test_alembic_baseline.py] [source: scripts/podium-backup.sh] [source: wiki/raw/sessions/2026-06-11-podium-023b-alembic-backup.md]

## Alembic baseline

`tests/test_alembic_baseline.py` upgrades a fresh SQLite DB through Alembic head using `PODIUM_DB_PATH`, then compares the migrated schema with an in-memory DB created from `web.api.schema.SCHEMA_SQL`. The fingerprint compares table names, columns, foreign keys, and indexes, excluding SQLite internals and `alembic_version`. A second test asserts the migration directory remains a single linear chain rooted at `0001_initial`. [source: tests/test_alembic_baseline.py]

The migration README now documents the rule: schema changes ship as a new revision, never by editing a prior revision, and developers must run `uv run pytest tests/test_alembic_baseline.py` before merging schema changes. [source: web/api/migrations/README.md]

Alembic `env.py` now calls `fileConfig(..., disable_existing_loggers=False)` so running Alembic inside pytest does not disable project loggers and break later `caplog` assertions. [source: web/api/migrations/env.py] [source: wiki/raw/sessions/2026-06-11-podium-023b-alembic-backup.md]

## Backup mechanism

`rsnapshot` was absent on the host, so #023b uses the documented cron fallback. `/etc/cron.d/podium-backup` runs `/home/james/symphony/scripts/podium-backup.sh` daily at 02:17 as `james`, logging to `runs/podium-backup.log`. A snapshot of the installed cron file is stored in `wiki/raw/podium-backup.cron`. [source: wiki/raw/podium-backup.cron]

`scripts/podium-backup.sh` resolves the active DB path and run-log root via `web.api.db.resolve_db_path()` and `resolve_run_log_root()`. It uses SQLite's `.backup` command to write `/backup/podium-YYYY-MM-DD.db`, optionally tars the run-log directory to `/backup/podium-runs-YYYY-MM-DD.tar.gz`, and deletes Podium backup artifacts older than 14 days. This protects both repo-root fallback mode and future `/var/lib/symphony/podium.db` mode with the same script. [source: scripts/podium-backup.sh]

`web/README.md` now documents the backup mechanism, 14-day retention, restore procedure, and the accepted weakness that local backups do not provide off-host replication. [source: web/README.md]

## Restore drill and verification

The session created `/backup/podium-2026-06-11.db` and compared it against the active DB. Schema matched and row counts matched: `alembic_version=1`, `binding=2`, `issue=17`, `run=6`, `skill=7`. Full verification passed with `uv run pytest` reporting 554 passed and 1 skipped; the issue verification then confirmed the backup file. [source: wiki/raw/sessions/2026-06-11-podium-023b-alembic-backup.md] [source: .kanban/issues/023b-podium-alembic-and-backup.md]

## Dev-tooling pin

During verification, pytest 9 / pytest-asyncio 1 changed logging behavior enough that existing `caplog` assertions failed after Alembic ran. The dev optional dependencies are now pinned to pytest 8.x and pytest-asyncio 0.x until tests are updated for newer logging behavior. [source: pyproject.toml] [source: uv.lock] [source: wiki/raw/sessions/2026-06-11-podium-023b-alembic-backup.md]

## Follow-ups

- Off-host replication remains absent by design for v1; local backups do not protect against full host loss. [source: web/README.md]
- If `/var/lib/symphony/` is created later, migrate the repo-root fallback DB first or Podium may resolve to an empty default DB after restart. [source: web/api/db.py] [source: wiki/raw/sessions/2026-06-11-podium-023b-alembic-backup.md]

## Claims

C-0092 .. C-0094 in [CLAIMS.md](../CLAIMS.md).
