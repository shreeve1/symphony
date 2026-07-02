---
id: 127
title: Add issue.origin column + migration 0014
status: done
blocked_by: []
parent: null
priority: 0
created: 2026-07-02
updated: 2026-07-02
actor: ralph
---

## What to build

Add an `origin` provenance column to the `issue` table so the engine can tell
operator-created issues apart from patrol/externally-created ones. This is the
schema foundation for the ADR-0020 verified-close scoping fix (operator issues
must stop auto-closing; only patrol issues should).

- New Alembic revision `web/api/migrations/versions/0014_issue_origin.py`,
  `down_revision = "0013_issue_hold"`:
  - `upgrade()`: add `origin TEXT NOT NULL DEFAULT 'operator'` with a
    `CHECK (origin IN ('operator','patrol'))` constraint on the `issue` table.
    SQLite cannot add a CHECK constraint via `ALTER TABLE ADD COLUMN` with a
    table-level CHECK, so follow the batch/table-rebuild pattern already used by
    `0008_fix_issue_archived_check.py` (batch_alter_table) to land the column
    with its CHECK.
  - Backfill in the same `upgrade()`: `UPDATE issue SET origin='patrol' WHERE
    external_id IS NOT NULL` (existing patrol/external rows become honest).
  - `downgrade()`: drop the `origin` column (reversible).
- Update `web/api/schema.py`:
  - Add the `origin` column to `SCHEMA_SQL` (fresh-DB path) matching the
    migration exactly, including the CHECK.
  - Bump `INITIAL_REVISION` to `"0014_issue_origin"`.

Match the existing column/CHECK style in `schema.py` (see `hold`, `auto_land`,
and the `state`/`priority` CHECK columns).

## Acceptance criteria

- [x] `web/api/migrations/versions/0014_issue_origin.py` exists with
      `down_revision = "0013_issue_hold"`, adds `origin` with the two-value
      CHECK, and backfills `external_id IS NOT NULL` rows to `'patrol'`.
- [x] `downgrade()` drops the `origin` column (migration is reversible).
- [x] `web/api/schema.py` SCHEMA_SQL includes the `origin` column with the same
      `NOT NULL DEFAULT 'operator' CHECK (origin IN ('operator','patrol'))`.
- [x] `INITIAL_REVISION == "0014_issue_origin"` in `schema.py`.
- [x] A fresh DB built from SCHEMA_SQL and a migrated DB have identical `issue`
      table pragma (the alembic baseline test asserts this parity).

## Verification

`PATH="$HOME/.local/bin:$PATH" uv run pytest web/api/tests/test_alembic_baseline.py -q`

## Blocked by

None - can start immediately

## Implementation Notes

Added migration `0014_issue_origin.py` (`down_revision = 0013_issue_hold`) using a
direct `ALTER TABLE issue ADD COLUMN origin TEXT NOT NULL DEFAULT 'operator'
CHECK (origin IN ('operator','patrol'))`. SQLite accepts a *column-level* CHECK on
ADD COLUMN (the issue's table-rebuild note applies to *table-level* CHECKs), so the
simpler ADD COLUMN path matches the 0011/0013 style and keeps downgrade trivially
reversible. `upgrade()` backfills `origin='patrol'` for `external_id IS NOT NULL`
rows; `downgrade()` drops the column. Both idempotent via `_issue_columns()`.
`schema.py`: added the identical column to SCHEMA_SQL and bumped
`INITIAL_REVISION` to `0014_issue_origin`. Verified fresh-vs-migrated `issue`
pragma parity. Verification `uv run pytest web/api/tests/test_alembic_baseline.py -q`
passes (exit 0).
