# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

## #93 Schedule foundations — 2026-06-21

**What changed:** Added shared maintenance-window computation, `next_window` schedule parsing, and Podium single-blob latest control-line selection.
**Files:** `schedule.py`, `scheduler/__init__.py`, `tests/test_schedule.py`, `tests/test_scheduler.py`, `.kanban/issues/093-schedule-foundations-next-window-prefer-last.md`
**Decisions:** Window constants now live in `schedule.py`; scheduler keeps compatibility aliases but delegates to `schedule.next_maintenance_window`. `prefer_last` remains opt-in and is enabled only for Podium-style single-blob comments.
**Verification:** `uv run pytest tests/test_schedule.py tests/test_scheduler.py -q` (226 passed); LSP diagnostics clean for touched Python files.
