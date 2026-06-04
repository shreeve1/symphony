# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

## #001 Role-based Tracker Contract — 2026-06-04

**Result:** Blocked after mandatory fresh review.
**What changed:** Added Symphony-owned tracker contract/Plane adapter/prompt renderer, removed homelab pythonpath, and rewired scheduler/poller/reconciler imports and role checks.
**Verification:** `uv run pytest` passed (346 tests). LSP diagnostics only reported environment missing-import noise for root modules/pytest; `uv run --extra dev python` imports succeeded.
**Blocker resolved:** Plan completion now skips adding `TrackerRole.APPROVAL_REQUIRED` when that optional role is omitted; regression-covered by `test_plan_mode_skips_missing_optional_approval_required_label`.
**Verification:** `uv run pytest` passed (347 tests). Critical LSP diagnostics for `scheduler.py` and `tests/test_scheduler.py` reported no diagnostics.

## #002 Tracker Adapter seam — 2026-06-04

**Result:** Completed after mandatory fresh review (`RALPH_REVIEW: PASS_WITH_NOTES`).
**What changed:** Added `TrackerAdapter` / `PlaneTrackerAdapter`, moved Plane polling and HTTP transport behind the adapter, and rewired scheduler/blocked reconciler/main to depend on the tracker seam.
**Files:** `plane_adapter.py`, `plane_poller.py`, `scheduler.py`, `blocked_reconciler.py`, `main.py`, `tests/test_plane_poller.py`
**Decisions:** Kept `plane_poller.py` as a compatibility wrapper so existing imports continue to work while engine code uses `TrackerAdapter`.
**Conventions established:** Engine modules should use tracker lifecycle methods (`list_candidates`, `list_issues_by_state`, `get_issue`, `list_comments`, `add_comment`, `transition_state`, label ops) rather than Plane paths/transports directly.
**Verification:** `uv run pytest` passed (348 tests). Critical LSP diagnostics for touched files reported no diagnostics.
**Notes for next iteration:** `PlaneAdapter` remains as a compatibility alias to `PlaneTrackerAdapter`; future slices may migrate tests/imports gradually if desired.

