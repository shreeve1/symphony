---
id: 114
title: Add issue.auto_land column (schema + Alembic 0011)
status: done
blocked_by: [105]
locks: [schema]
priority: 1
created: 2026-06-24
updated: 2026-06-24
action_reviewed: 2026-06-24
actor: ralph
---

## What to build

Per ADR-0023, persist per-issue auto-land provenance on the Podium `issue` row.
This is the enabler for the review phase's provenance-gated terminal (118): a
slicer-authored issue (`auto_land = true`) may auto-merge on a passing review;
everything else (`false`) keeps the operator merge gate.

- Add to the `issue` table in `web/api/schema.py` (NOT NULL with default, mirrors
  `worktree_active`/`approval_required`):
  - `auto_land BOOLEAN DEFAULT FALSE` — `true` only for issues authored by the
    `/podium-issues` slicer; UI/operator-created issues default `false`.
- Add Alembic migration `web/api/migrations/versions/0011_issue_auto_land.py`
  (revises `0010` — ADR-0021 slice 105's `blocked_by`+`locks` migration): add the
  column; downgrade drops it. Update `web/api/schema.py` `INITIAL_REVISION` only if
  the baseline pin convention requires it; update baseline test pins if they assert
  head/columns.
- Expose it on the read path (`tracker_podium._row_to_issue` / `get_issue`):
  `auto_land` parsed as `bool`, defaulting `False` on NULL.

## Acceptance criteria

- [x] `issue.auto_land` exists in `schema.py` with a `FALSE` default.
- [x] Migration 0011 (revises 0010) applies and reverts cleanly; runtime schema ==
      migration schema.
- [x] Tracker reads `auto_land` as `bool`; NULL → `False`.

## Verification

`uv run pytest tests/test_alembic_baseline.py -q`
and `uv run python -m py_compile web/api/schema.py tracker_podium.py`

## Implementation Notes

Added `issue.auto_land` to runtime schema and Alembic head `0011`, bumped `INITIAL_REVISION`, and coerced the tracker read path to a bool defaulting false. Added a regression assertion for the default false read-path.
