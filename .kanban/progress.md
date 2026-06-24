# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

## #105 Add issue.blocked_by + issue.locks columns — 2026-06-24

**What changed:** Added nullable JSON columns `issue.blocked_by` and `issue.locks`, Alembic migration 0010, and Podium read-path coercion.
**Files:** `web/api/schema.py`, `web/api/migrations/versions/0010_issue_blocked_by_locks.py`, `tracker_podium.py`, `web/api/tests/test_alembic_baseline.py`, `tests/test_tracker_podium.py`
**Decisions:** Store dependency ids and lock labels as JSON text on the issue row; malformed/blank values read as empty lists.
**Conventions established:** `blocked_by` is exposed as `list[int]`; `locks` is exposed as `list[str]`.
**Verification:** `uv run pytest web/api/tests/test_alembic_baseline.py tests/test_alembic_baseline.py -q` and `uv run python -m py_compile web/api/schema.py tracker_podium.py` passed; `tests/test_tracker_podium.py` also passed.
**Action review:** 2026-06-24 fresh review diffed `fb2211ce7c54454dd3e83c28f324e13275b0028f..HEAD`, read all changed files, found no gaps, reran verification, and found 0 LSP diagnostics on touched Python files.
