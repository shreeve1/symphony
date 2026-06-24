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

## #113 Merge-contention fix — 2026-06-24

**What changed:** `merge_worktree` now rescues non-conflicting FF-only merge failures by rebasing the worktree branch onto the advanced base branch, then retrying the FF merge once.
**Files:** `web/api/worktree.py`, `web/api/tests/test_worktree.py`
**Decisions:** Rebase conflicts abort and return the existing block message, leaving the worktree intact for manual inspection; no agent re-dispatch/counter was added.
**Conventions established:** Worktree landing stays deterministic and local-ref-only: one in-process rebase retry on non-FF, block on conflict.
**Verification:** `uv run pytest web/api/tests/test_worktree.py -q` passed; `uv run ruff check web/api/worktree.py web/api/tests/test_worktree.py` and `uv run python -m py_compile web/api/worktree.py web/api/tests/test_worktree.py` passed; LSP diagnostics found 0 errors in touched files.
**Action review:** 2026-06-24 fresh review diffed `38d2e4452016fb8b924fc70cc81858374ddfc640..HEAD`, read all changed files, reran verification, and passed.

## #110 UI dependency/lock gate chips — 2026-06-24

**What changed:** Podium issue payloads now include dependency/lock gate metadata, and the board card plus flyout render read-only `Waiting on #N` / `Locked: <label>` chips for gated `todo` issues.
**Files:** `web/api/main.py`, `web/frontend/lib/api.ts`, `web/frontend/components/IssueCard.tsx`, `web/frontend/components/KanbanBoard.tsx`, `web/frontend/components/IssueFlyout.tsx`, `web/frontend/components/NewIssueModal.tsx`, `web/frontend/tests/dependency-chip.spec.ts`
**Decisions:** Missing blocker ids stay treated as satisfied to match the scheduler gate; card chips derive live state from the current board list while flyout chips use API-derived detail fields.
**Conventions established:** Gate chips are display-only spans; dependency and lock gates never add a new issue state or operator control.
**Verification:** `pnpm -C web/frontend exec playwright test dependency-chip.spec.ts` passed; `pnpm -C web/frontend exec tsc --noEmit`, `uv run ruff check web/api/main.py`, and `uv run python -m py_compile web/api/main.py` passed; LSP found 0 critical diagnostics in touched files.
**Action review:** 2026-06-24 fresh review diffed `db09ac745b6162601ffa5e0fba0644eb371f1960..HEAD`, read all changed files, reran verification, and passed.

## #111 MANUAL deploy P2 conflict-free parallel dispatch — 2026-06-24

**What changed:** Re-reviewed the blocked manual deploy; all dependencies are done, but live services were not touched.
**Files:** `.kanban/issues/111-MANUAL-deploy-dependencies.md`
**Blocker:** The remaining gate is not confirmation friction: the target combines hard-to-reverse live migration/restarts with prose-only concurrent-dispatch observation, so there is no exact executable verification command that can exit 0 for unattended DONE.
**Notes for next iteration:** Operator marked issue done by override; unattended worker did not run live migration/restarts/calibration, so confirm out-of-band before relying on production being updated.

## #112 Skill /podium-issues plan slicer — 2026-06-24

**What changed:** Repurposed `/podium-issues` into a direct plan-slice-to-Podium workflow backed by `web.cli.podium issues create-from-plan`; the CLI resolves the binding from cwd, creates slices in dependency order, maps dependent `blocked_by` keys to real Podium ids, and writes `locks` inline. Retired the old `.kanban` folder mirror behavior.
**Files:** `.claude/skills/podium-issues/SKILL.md`, `web/cli/podium.py`, `web/cli/podium_issues.py`, `web/cli/tests/test_podium_issues.py`, `.kanban/issues/112-podium-issues-plan-slicer-skill.md`
**Decisions:** Keep LLM slicing/operator approval in the skill text; keep Python as the boring sink that consumes an approved YAML slice spec and writes Podium rows directly.
**Conventions established:** Podium plan slicing uses slice keys only inside the YAML spec; persisted dependencies are real Podium ids.
**Verification:** `PATH="$HOME/.local/bin:$PATH" uv run pytest web/cli/tests/test_podium_issues.py -q` passed; LSP diagnostics found 0 issues in touched Python files.
**Action review:** 2026-06-24 fresh review diffed `a9f20d03c149d3953345cac213f184aa77a88443..HEAD`, reran verification, ran ruff, checked criteria, and passed.

## #114 Add issue.auto_land column — 2026-06-24

**What changed:** Added `issue.auto_land` with `BOOLEAN NOT NULL DEFAULT FALSE`, Alembic migration 0011, `INITIAL_REVISION` bump, and tracker bool coercion for the read path.
**Files:** `web/api/schema.py`, `web/api/migrations/versions/0011_issue_auto_land.py`, `tracker_podium.py`, `tests/test_tracker_podium.py`, `.kanban/issues/114-issue-auto-land-column.md`
**Decisions:** Keep `auto_land` false by default; only future slicer/write-path work should set it true.
**Conventions established:** `auto_land` is exposed from `PodiumTrackerAdapter` as a Python `bool`; NULL/missing values read as `False`.
**Verification:** `uv run pytest tests/test_alembic_baseline.py -q` and `uv run python -m py_compile web/api/schema.py tracker_podium.py` passed; `tests/test_tracker_podium.py` and an upgrade/downgrade smoke for 0011 also passed. LSP diagnostics only reported environment-only missing imports for Alembic/SQLAlchemy in the migration.
**Action review:** 2026-06-24 fresh review diffed `d5bd697adf9f6976ac6ae0f92461a5eb6309a023..HEAD`, read all changed files, reran verification, and passed.

## #115 Carry auto_land through create/patch API — 2026-06-24

**What changed:** Added `auto_land` to Podium issue create/patch payloads, persisted it on insert/update, returned it from list/detail payloads, and coerced row values to booleans.
**Files:** `web/api/main.py`, `web/api/tests/test_issue_create.py`, `web/api/tests/test_issue_patch.py`, `.kanban/issues/115-auto-land-write-path.md`
**Decisions:** Keep `auto_land` false unless explicitly set by trusted creator paths; operator/UI-created issues remain non-auto-landing by omission.
**Conventions established:** API `auto_land` follows existing boolean-field behavior (`worktree_active`, `approval_required`): create defaults false, patch accepts explicit bool and rejects null.
**Verification:** `uv run pytest web/api/tests/test_issue_create.py web/api/tests/test_issue_patch.py -q` passed with PATH including `$HOME/.local/bin`; ruff, py_compile, and LSP diagnostics passed for touched Python files.
**Action review:** 2026-06-24 fresh review diffed `a795b80fef512771fae8a5d9d7c25f5963a85219..HEAD`, read changed files, reran verification, ran ruff, checked criteria, and passed.

## #116 REVIEW_PREAMBLE renderer constant — 2026-06-24

**What changed:** Added `REVIEW_PREAMBLE` and `render_review_prompt(issue)` so review dispatch can render the review contract, issue body, and centralized output contract without skill or WORKFLOW loading.
**Files:** `prompt_renderer.py`, `tests/test_prompt_renderer.py`, `.kanban/issues/116-review-preamble-renderer-constant.md`
**Decisions:** Keep review prompting as an engine-owned renderer constant; expose it through a sibling render helper rather than overloading normal implement dispatch.
**Conventions established:** Review prompts must mandate exact `## Verification`, permit in-place fixes, and end with one `SYMPHONY_RESULT: done|blocked` marker.
**Verification:** `uv run pytest tests/test_prompt_renderer.py -q` and `uv run python -m py_compile prompt_renderer.py` passed; ruff and LSP diagnostics passed for touched Python files.
**Action review:** 2026-06-24 fresh review diffed `5fc06962b3bbc71ba22bacfb9fd6735bc574d47c..HEAD`, read all changed files, reran verification, ran ruff, checked criteria, and passed.

## #117 Extract process-neutral land_worktree — 2026-06-24

**What changed:** Added `land_worktree` as a process-neutral merge-and-cleanup helper, refactored `_maybe_merge_worktree` to call it, and re-exported it through `worktree_facade.py`.
**Files:** `web/api/worktree.py`, `web/api/main.py`, `worktree_facade.py`, `web/api/tests/test_worktree.py`, `.kanban/issues/117-land-worktree-process-neutral.md`
**Decisions:** Keep issue-state mutation and dirty-worktree redispatch in the API wrapper; `land_worktree` only runs git merge/rebase-retry/cleanup and returns a block reason.
**Conventions established:** Scheduler/importer-facing worktree helpers go through `worktree_facade.py`.
**Verification:** `uv run pytest web/api/tests/test_worktree.py -q` and `uv run python -m py_compile web/api/worktree.py web/api/main.py worktree_facade.py` passed; ruff and LSP diagnostics found 0 touched-file errors.
**Action review:** 2026-06-24 fresh review diffed `ca648d25735927929a4df53a8d452f10674e56d1..HEAD`, read all changed files, reran verification, and passed with notes about formatting-only hunks.
