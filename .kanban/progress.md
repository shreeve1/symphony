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

**Result:** Completed after actionable review fix.
**What changed:** Added per-run worktree helpers, scheduler semaphore cap=1, worktree-based auto-commit plumbing, and tests for worktree cleanup/branch retention.
**Fixes:** `PiAgentAdapter.__call__` now forwards `worktree_path` into `run_agent`; scheduler removes deterministic orphan worktrees before redispatch and during stale running reconciliation.
**Files:** `agent_runner.py`, `scheduler.py`, `tests/test_agent_runner.py`, `tests/test_scheduler.py`, `.kanban/issues/004-run-worktree-lifecycle-cap1.md`
**Decisions:** Existing orphan worktrees for the same deterministic run id are treated as stale crash residue and force-removed before a new dispatch.
**Conventions established:** Production agent adapters must preserve the scheduler `worktree_path` keyword so agents run in their isolated branch checkout.
**Verification:** `uv run pytest` passed (353 tests). Critical LSP diagnostics for touched files reported no diagnostics.

## #002 Tracker Adapter seam actionable review — 2026-06-04

**Result:** Action-reviewed; no code gaps found.
**What checked:** Worker diff `0c082ce53e54b42ced54c54cd9cbab99223ab3b0..HEAD` was empty; audited historical #002 diff and current adapter/scheduler/reconciler files.
**Verification:** `uv run pytest` passed (353 tests). Critical LSP diagnostics for #002-touched files reported no diagnostics.

## #003 Agent Adapter seam actionable review — 2026-06-04

**Result:** Action-reviewed; no code gaps found.
**What checked:** Worker diff `d170898f000c984232d1826c2836b002169366a3..HEAD` was empty; audited historical #003 diff and current agent adapter/scheduler/main files.
**Verification:** `uv run pytest` passed (353 tests). Critical LSP diagnostics for #003-touched files reported no diagnostics.


## #005 Startup reconcile + reaper — 2026-06-04

**Result:** Completed after mandatory fresh review (`RALPH_REVIEW: PASS`).
**What changed:** Added startup reconciliation before the scheduler loop, reaping orphan worktrees, stale per-run tmux sessions, and Running tracker issues with no live run.
**Files:** `scheduler.py`, `run_worktree.py`, `main.py`, `tests/test_scheduler.py`, `tests/test_run_worktree.py`, `tests/test_main.py`
**Decisions:** Running issues with stale/no-live claims are reconciled by moving them to Blocked and cleaning deterministic run resources rather than blindly redispatching on startup.
**Conventions established:** Reaper matching uses the #004 `run-<id>` naming scheme across tracker identifiers, worktree paths, branches, and tmux session names.
**Verification:** `uv run pytest` passed (363 tests). Critical LSP diagnostics for touched files reported no diagnostics.
**Notes for next iteration:** #010 can rely on startup reconciliation preserving semaphore correctness after process restarts.

## #006 git-ref plan→build handoff — 2026-06-04

**Result:** Completed after mandatory fresh review (`RALPH_REVIEW: PASS`).
**What changed:** Plan handoff comments now carry the deterministic run branch ref instead of an absolute filesystem path; build runs validate that ref, create their worktree from it, and validate `plans/<slug>.md` inside the build worktree.
**Files:** `scheduler.py`, `tests/test_scheduler.py`, `.kanban/issues/006-git-ref-plan-build-handoff.md`
**Decisions:** Valid reported plan artifacts are auto-committed to the run branch before the plan handoff is posted, so the retained local branch is the artifact store.
**Conventions established:** Plan→build handoff is git-ref based; `_PLAN_HANDOFF_MARKER` comments should end with a local `symphony/run-<id>` branch ref, not a filesystem path.
**Verification:** `uv run pytest` passed (364 tests). Critical LSP diagnostics for touched files reported no diagnostics.
**Notes for next iteration:** Build-mode consumers can assume handoff plan files are validated in the run worktree after branch checkout.

## #007 bindings.yml multi-project config — 2026-06-04

**Result:** Blocked by mandatory fresh review (`RALPH_REVIEW: FAIL`).
**What changed before block:** Added `bindings.yml` loading into project bindings, config defaults for approval/landing policy, per-binding tracker contract/repo/base/default_agent fields, multi-binding main loop scaffolding, base-branch worktree creation, and tests.
**Verification before block:** `uv run pytest` passed (371 tests). Critical LSP diagnostics for touched files reported no diagnostics.
**Blocker:** Review found `default_agent: claude` is rejected by `main.py`, per-issue `agent:claude` / `agent:pi` override is not wired into dispatch, and approval policy default-off is loaded but not enforced by scheduler gating.

## #009 claude Agent Adapter (tmux send-keys) — 2026-06-05

**Result:** Completed after mandatory fresh review (`RALPH_REVIEW: PASS_WITH_NOTES`).
**What changed:** Added `ClaudeAgentAdapter` with private per-run tmux socket/session lifecycle, nonce done-marker polling, pane scraping before the marker, and cleanup. Added `RoutingAgentAdapter` so binding defaults and `agent:claude` / `agent:pi` issue labels select the correct adapter.
**Files:** `agent_runner.py`, `main.py`, `tests/test_agent_runner.py`, `tests/test_main.py`, `.kanban/issues/009-claude-agent-adapter-tmux.md`
**Decisions:** Claude completion is marker-based; stdout returned to the scheduler is pane content before the marker so existing `SYMPHONY_RESULT` / `SYMPHONY_SUMMARY` parsing and side-effect backstops remain scheduler-owned.
**Conventions established:** Claude tmux sessions use the #004 deterministic run id through `tmux_session_name(run_id)` and private socket `symphony-run-<run_id>`.
**Verification:** `uv run pytest` passed (374 tests). Critical LSP diagnostics for touched files reported no diagnostics.
**Notes for next iteration:** Fresh review noted a non-blocking robustness follow-up: `_kill` could suppress `OSError` if tmux itself is unavailable during cleanup.

## #010 Concurrent dispatcher at cap=2–3 — 2026-06-05

**Result:** Blocked by mandatory fresh review (`RALPH_REVIEW: FAIL`).
**What changed before block:** Added configurable `run_cap`, concurrent `run_loop` task management, semaphore initialization, and dispatcher tests.
**Verification before block:** Implementation worker reported `uv run pytest` passed (383 tests) and critical LSP diagnostics for touched files reported no diagnostics.
**Blocker:** Review found dispatcher task scheduling can hot-spin, semaphore acquisition is nested so cap=2 can serialize, cancellation/tmux cleanup coverage is incomplete, and tests do not objectively prove overlapping concurrent runs/cap+1 waiting/worktree isolation.

## #007 bindings.yml multi-project config actionable review — 2026-06-05

**Result:** Completed after mandatory fresh review (`RALPH_REVIEW: PASS_WITH_NOTES`).
**What changed:** Resolved #007 blocker by letting `RoutingAgentAdapter` handle `default_agent: claude` and `agent:*` overrides, moving approval-required filtering from the Plane adapter into scheduler policy checks, and making plan-mode approval-required labels opt-in on binding approval policy.
**Files:** `main.py`, `plane_adapter.py`, `scheduler.py`, `tests/test_plane_poller.py`, `tests/test_scheduler.py`, `.kanban/issues/007-bindings-yml-multi-project.md`
**Decisions:** `PlaneTrackerAdapter.list_candidates()` returns approval-required Todo issues; scheduler decides whether to hold them based on the binding approval policy.
**Conventions established:** Approval-required labels are only a scheduler hold when the binding approval policy is enabled; default-off bindings still dispatch those issues.
**Verification:** `uv run pytest` passed (385 tests). Critical LSP diagnostics for touched files reported no diagnostics.
**Notes for next iteration:** #008 can assume multi-binding config and agent routing are complete; #010 remains blocked independently on dispatcher concurrency concerns.

## #008 WORKFLOW.md mandatory renderer — 2026-06-05

**Result:** Completed after mandatory fresh review (`RALPH_REVIEW: PASS`).
**What changed:** Made repo-root `WORKFLOW.md` mandatory for prompt rendering, removed label-selected prompt fragments/mode directives from the renderer, and made the scheduler block before dispatch when the workflow file is missing or unreadable.
**Files:** `prompt_renderer.py`, `main.py`, `scheduler.py`, `tests/test_prompt_renderer.py`, `tests/test_main.py`, `tests/test_scheduler.py`, `.kanban/issues/008-workflow-md-mandatory-renderer.md`
**Decisions:** The renderer is now pure mechanism: `WORKFLOW.md` + issue variables + escaped issue/comment/schedule context. Mode remains an engine-owned variable and side-effect backstop input, not a renderer-selected instruction block.
**Conventions established:** Binding dispatch must pass the bound repo root to prompt rendering; missing `<repo>/WORKFLOW.md` is a hard pre-dispatch block with a Plane comment naming the file.
**Verification:** `uv run pytest` passed (388 tests). Critical LSP diagnostics for touched files reported no diagnostics. Fresh review reran `uv run pytest` and compile/import checks with a clean worktree.
**Notes for next iteration:** #011 can rely on project scaffolding creating a `WORKFLOW.md` stub because dispatch now refuses repos without one.
