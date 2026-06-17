# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

# Conventions & Decisions

- Keep Phase 1 architecture-review cleanups behavior-preserving: direct imports, stale-text removal, and docstring corrections only.
- For Podium prompt rendering, apply the skill directive once after branch-specific prompt assembly so resume and non-resume paths stay aligned.
- `main.build_binding_runtime(config, binding)` is the public single-binding runtime constructor; keep startup verification side effects in `_probe_binding` before construction.

# Iteration Log

## #059 Phase 1 — foundation cleanups — 2026-06-17

**What changed:** Completed eight root-scheduler micro-edits from the architecture review: hoisted `model_catalog` imports, replaced context-compaction reflection with direct imports/calls, removed dead `READY_PATTERN`, simplified `reconcile_stale_running`, consolidated Podium skill-directive prepend, and refreshed stale docstrings.
**Files:** `__init__.py`, `main.py`, `scheduler.py`, `claude_runner.py`, `prompt_renderer.py`, `notifier.py`, `code_version.py`, `.kanban/issues/059-phase1-foundation-cleanups.md`.
**Decisions:** Kept `import_module("tracker_podium")` lazy in `main.py` to defer the `web.api.db` edge for plane-only bindings.
**Conventions established:** Direct imports are preferred over reflection for owned modules when no import-cycle or optional-dependency boundary exists.
**Notes for next iteration:** Issue #060 can build on the cleaned runner imports; issue #066 remains blocked until #059 is done.

## #060 proc_runtime.py shared process-runtime module — 2026-06-17

**What changed:** Added `proc_runtime.py` as the neutral home for process liveness, process start-time, ANSI stripping, and runtime-dir constants; repointed `agent_runner.py` and `claude_runner.py` to the public helper names.
**Files:** `proc_runtime.py`, `agent_runner.py`, `claude_runner.py`, `tests/test_claude_runner.py`, `.kanban/issues/060-proc-runtime-shared-module.md`.
**Decisions:** Kept `AgentResult`, `AgentRunnerError`, and `CompletedLike` exported from `agent_runner.py`; only genuinely shared process/runtime primitives moved.
**Conventions established:** Shared runner primitives use public names in neutral modules before cross-runner reuse.
**Notes for next iteration:** Touched-file LSP can report stale `proc_runtime` missing-import diagnostics for newly-created root modules even while `uv run python` imports and full pytest pass; treat as LSP cache/environment noise unless runtime import fails.

## #061 Single worktree import facade — 2026-06-17

**What changed:** Added `worktree_facade.py` as the single compatibility shim for Podium worktree helpers and repointed the four root worktree call sites through it.
**Files:** `worktree_facade.py`, `agent_runner.py`, `claude_runner.py`, `scheduler.py`, `.kanban/issues/061-worktree-import-facade.md`.
**Decisions:** Used `import_module("worktree_facade")` at call sites to preserve lazy import behavior and keep Pyright diagnostics clean for the root-level facade.
**Conventions established:** Compatibility import shims shared across root modules should live in one facade, with call sites importing from that facade rather than repeating `web.api.*` fallback logic.
**Notes for next iteration:** `grep -rn "from web.api.worktree import" *.py` now intentionally matches only `worktree_facade.py`.

## #062 Extract pi-command + silent-exit helpers — 2026-06-17

**What changed:** Added `_build_pi_command` and `_silent_exit_result` in `agent_runner.py`, repointed local one-shot, remote one-shot, RPC, and probe command construction through the helper, and added focused tests.
**Files:** `agent_runner.py`, `tests/test_agent_runner.py`, `.kanban/issues/062-pi-command-silent-exit-helpers.md`.
**Decisions:** Kept local absolute `pi_bin`, remote basename `pi_name`, and remote skill skipping at call sites by passing `pi_bin` and `skill_source` explicitly into `_build_pi_command`.
**Conventions established:** Runner command-building helpers should accept path/skill decisions as inputs instead of embedding local-vs-remote policy.
**Notes for next iteration:** Issue #063 remains independently eligible; issue #064 stays blocked until #063 is done.

## #063 Small polish batch — renderer-shim rename, KNOWN_AGENTS, entity-decode — 2026-06-17

**What changed:** Renamed the scheduler prompt-renderer shim to `_invoke_renderer`, repointed config and routing agent checks at `model_catalog.KNOWN_AGENTS`, and extracted `_decode_entity_at` for schedule HTML entity decoding.
**Files:** `scheduler.py`, `config.py`, `agent_runner.py`, `schedule.py`, `.kanban/issues/063-small-polish-batch.md`.
**Decisions:** Kept `main.py`'s `_render_candidate_prompt` mapper unchanged because it maps candidates to renderer data and is not the scheduler shim.
**Conventions established:** Valid agent vocabulary now comes from `model_catalog.KNOWN_AGENTS`; schedule entity decoding should use `_decode_entity_at` while each caller owns quote-handling semantics.
**Notes for next iteration:** Issue #064 is now unblocked and can use `KNOWN_AGENTS` as the single agent vocabulary source.

## #064 tracker_types.py — single home for tracker vocabulary — 2026-06-17

**What changed:** Added `tracker_types.py` as the neutral home for `CandidateIssue`, `CommentPayload`, `IssuePayload`, label/state helpers, ISO parsing, candidate conversion, and Plane-style cursor/page helpers; moved the `TrackerAdapter` Protocol home to `tracker_adapter.py`; repointed Plane, Podium, scheduler, blocked reconciler, web API, and poller imports.
**Files:** `tracker_types.py`, `tracker_adapter.py`, `plane_adapter.py`, `tracker_podium.py`, `scheduler.py`, `blocked_reconciler.py`, `main.py`, `web/api/main.py`, `tests/test_plane_poller.py`, `.kanban/issues/064-tracker-types-vocabulary-home.md`.
**Decisions:** The tracker layering is now `tracker_contract → tracker_types → tracker_adapter → {plane_adapter, tracker_podium}`; `tracker_types.py` stays stdlib-only and must not import in-scope or `web.*` modules.
**Conventions established:** Tracker vocabulary dataclasses and parser helpers belong in `tracker_types.py`; adapter Protocol changes belong in `tracker_adapter.py`, not concrete adapter modules.
**Notes for next iteration:** Issue #068 can use `tracker_types.CandidateIssue` and the unified `_parse_iso`/label helpers without importing Plane or Podium concrete adapters.

**Actionable review:** Preserved Plane-path schema/default behaviour after the type move: `IssuePayload` still defaults to Todo via a neutral literal, and Plane candidate polling raises `PlanePollingSchemaError` for missing required issue fields. Verification: `uv run pytest` (883 passed, 2 skipped); touched-file LSP diagnostics clean.

## #065 Extract `_probe_binding` from runtime factory — 2026-06-17

**What changed:** Moved binding startup probes from `_build_binding_runtime` into `_probe_binding(config, binding)` and made `run_bindings_loop` call the probe before runtime construction.
**Files:** `main.py`, `tests/test_main.py`, `.kanban/issues/065-extract-probe-binding.md`.
**Decisions:** Kept probe behavior unchanged: local pi probe still runs only for non-remote pi bindings, Podium pi probe still resolves from `models.yml`, and remote reachability remains warning-only.
**Conventions established:** `_build_binding_runtime` is now pure runtime wiring; startup verification belongs in `_probe_binding` before adapter/router assembly.
**Notes for next iteration:** Issue #066 can promote the runtime factory API without carrying startup side effects.

**Actionable review:** Re-read the full implementation diff from `55fcd52dde913b3b5b41d6a3aabadf993c6475d6` through `HEAD`, verified `_probe_binding` owns startup verification side effects and `_build_binding_runtime` stays pure runtime wiring. Verification: `uv run pytest` (884 passed, 2 skipped); touched-file LSP diagnostics clean; `git diff --check` clean.

## #066 Promote `build_binding_runtime` + clean web/api reflection cluster — 2026-06-17

**What changed:** Renamed `_build_binding_runtime` to public `build_binding_runtime`, documented it as the side-effect-free single-binding constructor, and replaced Podium context-compaction `vars()` reflection with direct imports/calls.
**Files:** `main.py`, `web/api/main.py`, `tests/test_main.py`, `tests/test_trading_podium_dispatch.py`, `web/api/tests/test_context_compaction.py`, `.kanban/issues/066-public-build-binding-runtime-web-api-reflection.md`.
**Decisions:** Kept the factory in `main.py` for now; full extraction to a neutral runtime factory remains deferred. The legacy `uvicorn main:app` from `web/api` path needs an alias loader because `web/api/main.py` is already bound to `sys.modules["main"]` during that import mode.
**Conventions established:** Web/API compaction may import the public runtime constructor directly; private engine reflection via `vars(engine_main)`/`vars(compaction)` should stay absent from `web/api/main.py`.
**Notes for next iteration:** Issue #067 remains independently eligible; issue #068 can proceed from #064 without depending on this factory rename.

**Actionable review:** Diffed `858ba03a9993c668bb27a7511aef43f35d1deff9..HEAD`, read every changed file, verified all acceptance criteria, and fixed one legacy app-dir import regression in `web/api/main.py` with coverage in `web/api/tests/test_context_compaction.py`. Verification: `uv run pytest` (885 passed, 2 skipped), `grep -n "vars(engine_main)\|vars(compaction)" web/api/main.py` no matches, `uv run ruff check web/api/main.py web/api/tests/test_context_compaction.py` clean, `git diff --check` clean, touched-file LSP diagnostics clean.

## #067 Stop shipping Plane secret/env to podium-binding agents — 2026-06-17

**What changed:** Gated Plane callback env and `plane` helper shipping in `agent_runner.py` so Podium bindings no longer receive `SYMPHONY_PLANE_*`, `PLANE_DASHBOARD_URL`, or the helper, while Plane bindings keep the legacy callback surface.
**Files:** `agent_runner.py`, `tests/test_agent_runner.py`, `tests/test_remote_agent.py`, `.kanban/issues/067-plane-secret-deshipping-podium.md`.
**Decisions:** Tracker kind comes from the scoped `SymphonyConfig.bindings[0].tracker` for local/RPC dispatch and the explicit `ProjectBinding.tracker` for remote dispatch.
**Conventions established:** Podium agent status flows through output markers, not the `plane` helper; callback secrets and helpers stay Plane-only.
**Notes for next iteration:** Issue #068 can assume podium-binding agents no longer receive Plane callback secrets from `agent_runner.py`.

**Actionable review:** `git diff 444f5b0f2509e12a746d0c4250f72bb9e0636eaa HEAD` was empty at session start, so the review loop implemented the missing slice, read every changed file, and verified the full suite. Verification: `uv run pytest` (887 passed, 2 skipped); focused agent-runner/remote tests passed; touched-file LSP diagnostics clean.

## #068 Dedup resume-fallback retry block — 2026-06-17

**What changed:** Extracted `_dispatch_with_resume_fallback` so resumed dispatch exception and resumed nonzero-exit paths share the same fail-record/log/reset/re-render/retry/crash-block sequence.
**Files:** `scheduler.py`, `tests/test_dispatch_compaction.py`, `.kanban/issues/068-dedup-resume-fallback.md`.
**Decisions:** Kept fallback behavior local to `scheduler.py` for this slice; the helper returns a fresh fallback dispatch result bundle or a terminal `TickResult` when the fallback crashes.
**Conventions established:** Resume-fallback behavior has one implementation point; future `run_tick` decomposition should move the helper with the dispatch-execution slice rather than clone it.
**Notes for next iteration:** Issue #070 can decompose `run_tick` without carrying duplicate resume fallback branches.

**Actionable review:** `git diff 7ef70d10a61f5b90663c73f8a47ad671e99384de HEAD` was empty at review start, so the review loop implemented the missing slice. Verification: `uv run ruff check scheduler.py tests/test_dispatch_compaction.py`; `uv run pytest tests/test_dispatch_compaction.py -q` (7 passed); touched-file LSP diagnostics clean; `uv run pytest` (888 passed, 2 skipped); live `symphony-restart` verification completed.

## #069 Scope cooldown to _DispatchState — 2026-06-17

**What changed:** Removed the global Plane cooldown and legacy test-only scheduler globals; direct dispatch calls now create explicit `_DispatchState` instances, and cooldown read/write/clear paths use only that state.
**Files:** `scheduler.py`, `tests/test_scheduler.py`, `.kanban/issues/069-scope-cooldown-dispatchstate.md`.
**Verification:** `uv run ruff check scheduler.py tests/test_scheduler.py`, `uv run pytest tests/test_scheduler.py -q`, `uv run pytest`, and touched-file LSP diagnostics passed. Fresh review returned `RALPH_REVIEW: PASS_WITH_NOTES`.
**Blocker:** Mandatory live `symphony-restart` verification could not run because the harness blocked `sudo systemctl restart symphony-host.service` with `live-systemctl`, despite operator pre-approval. Issue remains blocked until live restart verification confirms `symphony_started`, `reconcile_startup_*`, and `dispatch_completed`.
