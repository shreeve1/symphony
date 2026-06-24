---
id: 105
title: Add issue.blocked_by + issue.locks columns (schema + Alembic 0010)
status: done
blocked_by: []
locks: [schema]
priority: 1
created: 2026-06-23
updated: 2026-06-24
actor: ralph
---

## What to build

Per ADR-0021 (P2 convergence), persist BOTH dependency ordering and co-run
mutual-exclusion on the Podium `issue` row, as two JSON columns in one migration.

- Add to the `issue` table in `web/api/schema.py` (both nullable):
  - `blocked_by TEXT` — JSON array of Podium issue ids, e.g. `[12, 15]`;
    NULL/`[]` = no deps.
  - `locks TEXT` — JSON array of free-text label strings, e.g.
    `["scheduler", "web-api"]`; NULL/`[]` = holds no locks (never co-run-excluded).
- Add Alembic migration `web/api/migrations/versions/0010_issue_blocked_by_locks.py`
  (revises 0009): add both columns; downgrade drops both. Update baseline test
  pins if they assert head/columns.
- Expose both on the read path (`tracker_podium._row_to_issue` / `get_issue`):
  `blocked_by` parsed as `list[int]`, `locks` parsed as `list[str]`; each defaults
  to `[]` on NULL/blank/bad JSON.

## Acceptance criteria

- [x] `issue.blocked_by` and `issue.locks` exist in `schema.py`; NULL allowed.
- [x] Migration 0010 applies and reverts cleanly; runtime schema == migration schema.
- [x] Tracker reads `blocked_by` as `list[int]` and `locks` as `list[str]`;
      NULL/blank/invalid → `[]`.

## Verification

`uv run pytest web/api/tests/test_alembic_baseline.py tests/test_alembic_baseline.py -q`
and `uv run python -m py_compile web/api/schema.py tracker_podium.py`

## Implementation Notes

Added nullable JSON-backed `issue.blocked_by` and `issue.locks` columns to runtime schema and Alembic head 0010. Podium issue reads now coerce dependency ids to `list[int]` and locks to `list[str]`, defaulting malformed or missing values to `[]`.
