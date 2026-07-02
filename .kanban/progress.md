# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

# Conventions & Decisions

- **Issue-table column additions:** prefer direct `ALTER TABLE issue ADD COLUMN`
  with a column-level CHECK (SQLite supports it) over the table-rebuild pattern;
  reserve the `0008` batch/rebuild approach for *table-level* CHECK repairs. Keep
  each column migration idempotent via a `_issue_columns()` guard and mirror the
  new column verbatim in `web/api/schema.py` SCHEMA_SQL, then bump
  `INITIAL_REVISION`. Fresh-DB (SCHEMA_SQL) and migrated-DB `issue` pragma must match.

# Iteration Log

## #127 Add issue.origin column + migration 0014 — 2026-07-02

**What changed:** Added `origin` provenance column (`operator`/`patrol`) to the
`issue` table via migration `0014_issue_origin` and mirrored it in SCHEMA_SQL.
Backfills `external_id IS NOT NULL` rows to `patrol`; downgrade drops the column.
**Files:** web/api/migrations/versions/0014_issue_origin.py, web/api/schema.py
**Decisions:** Used column-level CHECK on ADD COLUMN (not table rebuild) — simpler
and reversible; the issue's rebuild note only applies to table-level CHECKs.
**Notes for next iteration:** #128 threads `origin` through the create API +
`CandidateIssue`; #129 gates verified-close on `origin == 'patrol'`. Default is
`'operator'`, and anything not explicitly `'patrol'` must be fail-safe (no auto-close).

## #129 Gate verified-close on origin == patrol — 2026-07-02

**What changed:** Added `and candidate.origin == "patrol"` to the ADR-0020
verified-close guard so only patrol-origin issues auto-close on a `done` verdict;
operator-origin `done` falls through to the In Review terminal path.
**Files:** scheduler/__init__.py, tests/test_scheduler.py
**Decisions:** Fail-safe polarity — only explicit `'patrol'` auto-closes; operator/
None/unknown park in In Review. Updated the existing verified-close test to set
`origin="patrol"` explicitly (it relied on the `_candidate` default) and added an
operator-origin park-in-review test.
**Notes for next iteration:** origin provenance chain (#127 column → #128 plumbing
→ #129 gate) is complete.
