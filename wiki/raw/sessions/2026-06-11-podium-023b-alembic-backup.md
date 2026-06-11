# Session Capture: Podium #023b Alembic baseline and backup wiring

- Date: 2026-06-11
- Purpose: Capture durable results from Ralph issue #023b.
- Scope: Alembic baseline verification, backup cron wiring, restore drill evidence, and pytest dev-tooling pin discovered during verification.

## Durable Facts

- Podium now has `tests/test_alembic_baseline.py`, which upgrades a fresh SQLite DB through Alembic and compares table, column, foreign key, and index fingerprints with runtime `SCHEMA_SQL`. Evidence: `tests/test_alembic_baseline.py`.
- Alembic migration logging now preserves existing loggers by calling `fileConfig(..., disable_existing_loggers=False)`. Evidence: `web/api/migrations/env.py`.
- Podium migration rules are documented in `web/api/migrations/README.md`, including the rule that schema changes ship as new revisions and prior revisions are never edited. Evidence: `web/api/migrations/README.md`.
- `rsnapshot` was absent on the host, so backup wiring uses cron: `/etc/cron.d/podium-backup` runs `scripts/podium-backup.sh` daily as `james`. Evidence: `wiki/raw/podium-backup.cron`, `scripts/podium-backup.sh`.
- `scripts/podium-backup.sh` resolves the active Podium DB and run-log root through `web.api.db.resolve_db_path()` / `resolve_run_log_root()`, writes `/backup/podium-YYYY-MM-DD.db`, optionally archives runs to `/backup/podium-runs-YYYY-MM-DD.tar.gz`, and rotates both beyond 14 days. Evidence: `scripts/podium-backup.sh`.
- A manual backup and restore drill ran successfully: `/backup/podium-2026-06-11.db` was created, copied aside, and compared against the active DB; schema and row counts matched (`alembic_version=1`, `binding=2`, `issue=17`, `run=6`, `skill=7`). Evidence: `.kanban/issues/023b-podium-alembic-and-backup.md`, `.kanban/progress.md`.
- Existing tests require pytest 8.x / pytest-asyncio 0.x log-capture behavior; pytest 9 disabled existing loggers in a way that broke caplog assertions after Alembic ran. Dev dependencies are pinned below pytest 9. Evidence: `pyproject.toml`, `uv.lock`, `web/api/migrations/env.py`.
- Full verification after the fix passed: `uv run pytest` reported 554 passed, 1 skipped, and the backup fallback listed `/backup/podium-2026-06-11.db`. Evidence: `.kanban/issues/023b-podium-alembic-and-backup.md`, `.kanban/progress.md`.

## Decisions

- Use cron `.backup` instead of rsnapshot because `rsnapshot` is not installed on this host. Evidence: `wiki/raw/podium-backup.cron`, `web/README.md`.
- Keep backup resolution tied to the active DB path rather than hard-coding `/var/lib/symphony/podium.db`, so repo-root fallback mode is protected until `/var/lib/symphony/` becomes writable. Evidence: `scripts/podium-backup.sh`, `web/README.md`.

## Evidence

- `tests/test_alembic_baseline.py` — Alembic baseline and linear-chain tests.
- `web/api/migrations/env.py` — logger-preserving Alembic fileConfig change.
- `web/api/migrations/README.md` — migration rules.
- `scripts/podium-backup.sh` — backup implementation.
- `wiki/raw/podium-backup.cron` — installed cron snapshot.
- `web/README.md` — operator backup, retention, and restore docs.
- `.kanban/issues/023b-podium-alembic-and-backup.md` — issue completion notes.
- `.kanban/progress.md` — Ralph progress entry.

## Exclusions

- No secrets, `.env` contents, tokens, passwords, or private keys captured.
- No raw transcript captured.
- No live alert or notification verification fired.

## Open Questions And Follow-Ups

- Off-host replication remains absent by design for v1; local backups do not protect against full host loss.
- If `/var/lib/symphony/` is created later, confirm service DB migration from repo-root fallback before restart so Podium does not appear empty.
