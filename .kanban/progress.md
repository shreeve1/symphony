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

## #003 Agent Adapter seam (pi one-shot) — 2026-06-04

**Result:** Completed after mandatory fresh review (`RALPH_REVIEW: PASS`).
**What changed:** Added `AgentAdapter` and `PiAgentAdapter`, wired `main.py` to pass the pi adapter into `run_loop`, and updated scheduler typing/tests around the adapter seam.
**Files:** `agent_runner.py`, `main.py`, `scheduler.py`, `tests/test_agent_runner.py`, `tests/test_main.py`
**Decisions:** Kept `run_agent` as the pi one-shot implementation behind `PiAgentAdapter` so existing subprocess behavior and `AgentResult` output are unchanged.
**Conventions established:** Agent implementations expose the scheduler-compatible `AgentAdapter` call contract and return `AgentResult`; verdict parsing remains in scheduler on the returned stdout/stderr.
**Verification:** `uv run pytest` passed (349 tests). Critical LSP diagnostics for touched files reported no diagnostics.
**Notes for next iteration:** #009 can add a Claude adapter behind the same `AgentAdapter` contract without changing scheduler verdict parsing.

## #004 Run Worktree lifecycle at cap=1 — 2026-06-04

**Result:** Blocked after mandatory fresh review (`RALPH_REVIEW: FAIL`).
**What changed:** Initial implementation added per-run worktree helpers, scheduler semaphore cap=1, worktree-based auto-commit plumbing, and tests for worktree cleanup/branch retention.
**Verification:** Implementer ran `uv run pytest` (351 tests) and critical LSP diagnostics for touched files reported no diagnostics.
**Blocker:** Reviewer found production `PiAgentAdapter.__call__` does not pass `worktree_path` into `run_agent`, so pi still runs in the shared checkout. Reviewer also found crash/orphan recovery incomplete beyond timeout cleanup.
**Notes for next iteration:** Fix the adapter worktree propagation first, then add/clarify orphan recovery expectations before rerunning review.

