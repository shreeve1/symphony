# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

## #105 Add issue.blocked_by + issue.locks columns — 2026-06-24

**What changed:** Added nullable JSON columns `issue.blocked_by` and `issue.locks`, Alembic migration 0010, and Podium read-path coercion.
**Files:** `web/api/schema.py`, `web/api/migrations/versions/0010_issue_blocked_by_locks.py`, `tracker_podium.py`, `web/api/tests/test_alembic_baseline.py`, `tests/test_tracker_podium.py`
**Decisions:** Store dependency ids and lock labels as JSON text on the issue row; malformed/blank values read as empty lists.
**Conventions established:** `blocked_by` is exposed as `list[int]`; `locks` is exposed as `list[str]`.
**Verification:** `uv run pytest web/api/tests/test_alembic_baseline.py tests/test_alembic_baseline.py -q` and `uv run python -m py_compile web/api/schema.py tracker_podium.py` passed; `tests/test_tracker_podium.py` also passed.
**Action review:** 2026-06-24 fresh review diffed `fb2211ce7c54454dd3e83c28f324e13275b0028f..HEAD`, read all changed files, found no gaps, reran verification, and found 0 LSP diagnostics on touched Python files.

## #106 Gate dispatch on dependencies — 2026-06-24

**What changed:** `tracker_podium.list_candidates` now withholds `todo` issues whose `blocked_by` ids are not `done`/`archived`, keeps them in `todo`, and logs unresolved blocker ids while treating them as eligible.
**Files:** `tracker_podium.py`, `tests/test_scheduler.py`
**Decisions:** Dependency resolution uses one per-binding issue-state snapshot per candidate scan; unresolved blocker ids warn but do not wedge dispatch.
**Conventions established:** `blocked_by` gates scheduling only; `blocked` remains reserved for agent failures.
**Verification:** `uv run pytest tests/test_scheduler.py -q` passed; LSP diagnostics found 0 issues in touched Python files.
**Action review:** 2026-06-24 fresh review diffed `32b7a1576a3840a8df773d12e1e19e0a4c595728..HEAD`, read all changed files, found and repaired a page-cap dependency snapshot gap, reran verification, and passed.

## #107 Carry blocked_by + locks through create/patch API — 2026-06-24

**What changed:** Added `blocked_by` and `locks` to Podium issue create/patch payloads, persisted them as JSON, returned them as typed lists, and rejected dependency cycles with HTTP 400.
**Files:** `web/api/main.py`, `web/api/tests/test_issue_create.py`, `web/api/tests/test_issue_patch.py`
**Decisions:** API callers pass real Podium ids directly; no kanban-id mirror or translation was added.
**Conventions established:** `blocked_by`/`locks` are omitted-as-empty API lists; cycle validation applies to `blocked_by` only.
**Verification:** `uv run pytest web/api/tests/test_issue_create.py web/api/tests/test_issue_patch.py -q` passed; `uv run python -m py_compile web/api/main.py web/api/tests/test_issue_create.py web/api/tests/test_issue_patch.py` passed; LSP diagnostics found 0 issues in touched Python files.
**Action review:** 2026-06-24 fresh review diffed `4e761ed52dbd06d5bc3c8e5e058a6fa68e56dbfa..HEAD`, read all changed files, reran verification, and passed.

## #108 Isolation — worktree-per-run default-ON for local bindings — 2026-06-24

**What changed:** Local coding bindings now default dispatch/resume into deterministic per-issue worktrees, with `SYMPHONY_WORKTREE_DEFAULT=false` as the opt-out switch; remote bindings still run in their configured shared repo.
**Files:** `config.py`, `scheduler/__init__.py`, `tests/test_config.py`, `tests/test_scheduler.py`
**Decisions:** Default isolation applies to local coding bindings while preserving explicit `worktree_active` opt-in and remote no-worktree behavior; dispatch marks Podium rows `worktree_active=True` so existing landing/cleanup owns terminal removal.
**Conventions established:** Use `SymphonyConfig.worktree_default` / `SYMPHONY_WORKTREE_DEFAULT` for the global worktree-default kill switch.
**Verification:** `uv run pytest tests/test_scheduler.py web/api/tests/test_worktree.py -q`, `uv run pytest tests/test_config.py -q`, `uv run python -m py_compile config.py scheduler/__init__.py tests/test_config.py tests/test_scheduler.py`, and `uv run ruff check config.py scheduler/__init__.py tests/test_config.py tests/test_scheduler.py` passed; LSP diagnostics found 0 issues in touched Python files.
**Action review:** 2026-06-24 fresh review diffed `2e53a0547e23267f055adc95a789febfc2f6360c..HEAD`, read all changed files, reran verification, and passed.

## #109 Mutual exclusion — co-run lock gate — 2026-06-24

**What changed:** Dispatch reservation now tracks in-flight lock labels and skips candidates whose `locks` intersect with already reserved work; Podium candidates carry their `locks` through `CandidateIssue`.
**Files:** `tracker_types.py`, `tracker_podium.py`, `scheduler/__init__.py`, `tests/test_scheduler.py`
**Decisions:** The claimed-this-tick and held-lock sets share one in-memory `in_flight_locks` map keyed by issue id; release clears both id and locks.
**Conventions established:** Lock conflicts are scheduling filters only; issues stay `todo` and never transition to `blocked` because of locks.
**Verification:** `uv run pytest tests/test_scheduler.py -q` passed; `uv run ruff check tracker_types.py tracker_podium.py scheduler/__init__.py tests/test_scheduler.py`, `uv run python -m py_compile ...`, and LSP diagnostics passed.
**Action review:** 2026-06-24 fresh review diffed `26f86c75fe7406e58c15daff9f0e56747e18c62f..HEAD`, read all changed files, reran verification, and passed.
