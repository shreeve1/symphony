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
**Live verification:** This Ralph worker restarted `symphony-host.service` and confirmed `symphony_started code_sha=877438f`, `rpc_orphan_reap_done`, `pi_rpc_probe_ok`, `reconcile_startup_*`, `run_reconcile_*`, and `dispatch_completed` for the live scheduler. Verification: `uv run pytest` (887 passed, 2 skipped); touched-file LSP diagnostics clean; fresh review returned `RALPH_REVIEW: PASS`.
**Actionable review:** Re-read `git diff 877438f7f13c0fdc8ab4857b2d9c15033257aa27 HEAD`, inspected acceptance-scope code/tests, verified no cooldown/test-only globals remain, reran `uv run pytest` (887 passed, 2 skipped), and checked critical LSP diagnostics for `scheduler.py` and `tests/test_scheduler.py` clean.

## #070 Decompose the run_tick god-function — 2026-06-17

**What changed:** Split `scheduler.run_tick` into named stages for selection/reconcile, gates, dispatch preparation, agent execution, and terminal classification. `_classify_terminal` now owns terminal run-record finalization, blocked/review transitions, Question Park, archived-terminal, and clean-review handling; agent-crash handling stays in `_dispatch_run_tick_agent` because the exception occurs during dispatch.
**Files:** `scheduler.py`, `.kanban/issues/070-decompose-run-tick.md`.
**Verification:** `uv run pytest` (887 passed, 2 skipped), `uv run ruff check scheduler.py`, `uv run python -m py_compile scheduler.py`, touched-file LSP diagnostics clean for `scheduler.py`, fresh review `RALPH_REVIEW: PASS`, and live `symphony-host.service` restart verification on `code_sha=48fc0bb` with `reconcile_startup_*`, `run_reconcile_*`, `dispatch_completed`, `rpc_orphan_reap_done`, and `pi_rpc_probe_ok`.
**Conventions established:** Future scheduler decomposition should keep `run_tick` as orchestration over named stage helpers and keep terminal tracker/run side effects centralized in `_classify_terminal`.
**Notes for next iteration:** Issue #071 can split scheduler packaging on top of the staged `run_tick`; issue #072 remains independently eligible for executor inner-loop extraction.

**Actionable review:** Re-read `git diff 2fa4d62ae41abc60e597181c209068a3eeaf710c HEAD`, inspected every changed file, verified the staged helpers preserve the `run_tick` dispatch path, reran `uv run pytest` (887 passed, 2 skipped), `uv run ruff check scheduler.py`, `uv run python -m py_compile scheduler.py`, checked `scheduler.py` LSP diagnostics clean, and confirmed live journal evidence for `symphony_started code_sha=48fc0bb`, `reconcile_startup_*`, `run_reconcile_*`, and ongoing `dispatch_completed` lines.

## #071 Split scheduler.py into a scheduler/ package — 2026-06-17

**What changed:** Replaced root `scheduler.py` with a `scheduler/` package that preserves the package-level import surface, extracted pure marker parsing to `scheduler/markers.py`, extracted sanitization / summary extraction to `scheduler/sanitize.py`, and created concern-split placeholder modules for the remaining scheduler slices.
**Files:** `scheduler/__init__.py`, `scheduler/markers.py`, `scheduler/sanitize.py`, `scheduler/run_records.py`, `scheduler/selection.py`, `scheduler/schedule.py`, `scheduler/reconcile.py`, `scheduler/loop.py`, `scheduler/tick.py`, `.kanban/issues/071-split-scheduler-package.md`.
**Decisions:** Kept impure dispatch/reconcile/run-loop helpers in `scheduler/__init__.py` for this slice while the pure leaves move first, preserving `from scheduler import ...` compatibility for `main.py` and tests.
**Conventions established:** Future scheduler decomposition should move behavior behind submodule seams incrementally while `scheduler/__init__.py` re-exports the stable test and runtime import surface.
**Notes for next iteration:** Issue #072 remains independently eligible; future scheduler package slices can populate the placeholder modules without breaking import compatibility.
**Verification:** `uv run pytest` and `uv run pytest -q` (887 passed, 2 skipped), `uv run ruff check scheduler`, `uv run python -m py_compile scheduler/...`, `git diff --check`, touched-file LSP diagnostics clean, fresh review `RALPH_REVIEW: PASS`, and live `symphony-host.service` restart verification on `code_sha=32b186f` with `rpc_orphan_reap_done`, `pi_rpc_probe_ok`, `reconcile_startup_*`, `run_reconcile_*`, and `dispatch_completed`.
**Actionable review:** Re-read `git diff bc33a1c14450207b853e333a0772451c3f6b061a HEAD`, inspected every changed file, verified package import compatibility and acyclic submodule imports, reran `uv run pytest` (887 passed, 2 skipped), `uv run ruff check scheduler`, `uv run python -m py_compile scheduler/*.py`, checked touched-file LSP diagnostics clean, confirmed live restart journal evidence for `code_sha=32b186f`, and added `action_reviewed: 2026-06-17`.

## #072 Extract RPC and Claude dispatch inner loops — 2026-06-17

**What changed:** Extracted `_drain_rpc_events(process, deadline, run_id, ...)` returning `_DrainResult` from `agent_runner.run_pi_rpc_agent` so the function reads setup → loop → teardown. Extracted `_poll_claude_until_done(...)` returning `AgentResult | None` from `claude_runner.run_claude_agent` so the function reads setup → loop → teardown.
**Files:** `agent_runner.py`, `claude_runner.py`, `.kanban/issues/072-extract-rpc-claude-inner-loops.md`.
**Decisions:** `_DrainResult` is a frozen dataclass carrying `assistant_parts`, `stderr_parts`, `error_seen`, `event_exit_code`, `timed_out`, and `steer_offset`. `_poll_claude_until_done` returns `AgentResult | None` with a defensive `RuntimeError` guard for the unreachable `None` path in `run_claude_agent`. The steer-queue comment about pi RPC idle semantics stays in the drain docstring.
**Conventions established:** RPC event drain and Claude poll loop are named steps; `run_pi_rpc_agent` and `run_claude_agent` are orchestration over setup → extracted loop → teardown.
**Notes for next iteration:** No downstream issue is blocked by #072; later Claude/RPC lifecycle work can build on the extracted loop seams.
**Verification:** `uv run pytest` and `uv run pytest -q` (887 passed, 2 skipped), `uv run ruff check agent_runner.py claude_runner.py`, `uv run python -m py_compile agent_runner.py claude_runner.py`, `git diff --check`, touched-file LSP diagnostics clean, fresh review `RALPH_REVIEW: PASS`, and live `symphony-host.service` restart verification on `code_sha=5cc9b4a` with `rpc_orphan_reap_done`, `pi_rpc_probe_ok`, `reconcile_startup_*`, `run_reconcile_*`, and `dispatch_completed`.
**Actionable review:** Re-read `git diff 0cb80da2703c2f1c195d85c32ff1c6b1797f622b HEAD`, inspected every changed file, verified extracted loop behavior and no unrelated changes, reran `uv run pytest -q` (887 passed, 2 skipped), `uv run ruff check agent_runner.py claude_runner.py`, checked `git diff --check`, and confirmed touched-file LSP diagnostics clean.

## #073 Config tracker-neutral env dual-read — 2026-06-17

**What changed:** Added tracker-neutral `SYMPHONY_TRACKER_*` env aliases in `config.py`, with neutral-over-legacy precedence and legacy `PLANE_*` fallback kept for the live service unit. Added tracker-neutral accessor properties on `SymphonyConfig` and `ProjectBinding` while preserving Plane-named fields.
**Files:** `config.py`, `tests/test_config.py`, `.kanban/issues/073-config-tracker-neutral-dual-read.md`.
**Decisions:** New `SYMPHONY_TRACKER_*` env values win when both neutral and legacy names are set; existing `PLANE_*` names remain valid so `/home/james/symphony-host.env` and `symphony-host.service` do not need edits in this slice.
**Verification:** `uv run pytest` (889 passed, 2 skipped); `uv run ruff check config.py tests/test_config.py`; touched-file LSP diagnostics clean.
**Actionable review:** Initial implementation diff from `6ab45266bce534f3ea3023d44e316ade5982ad91` to `HEAD` was empty, so the review loop implemented the missing slice, read every changed file, verified all acceptance criteria, and added `action_reviewed: 2026-06-17`.

## #074 Tracker enum neutral names with Plane* aliases — 2026-06-17

**What changed:** Added canonical `TrackerState`, `TrackerLabel`, and `TrackerUserMapping` names in `tracker_contract.py`, retained `PlaneState`, `PlaneLabel`, `PlaneUserMapping`, and `PlaneContract` as compatibility aliases, and repointed tracker adapter, Podium tracker, and config annotations to canonical names.
**Files:** `tracker_contract.py`, `tracker_adapter.py`, `tracker_podium.py`, `config.py`, `tests/test_tracker_contract.py`, `.kanban/issues/074-tracker-enum-neutral-names.md`.
**Decisions:** Plane-prefixed names remain import-compatible aliases for one release while new shared tracker code uses canonical `Tracker*` names.
**Conventions established:** New tracker contract annotations should use `TrackerState`, `TrackerLabel`, and `TrackerUserMapping`; existing Plane importers may continue using aliases until the planned compatibility cleanup.
**Verification:** `uv run pytest` (891 passed, 2 skipped); `uv run ruff check tracker_contract.py tracker_adapter.py tracker_podium.py config.py tests/test_tracker_contract.py`; focused contract/Podium/config tests passed; touched-file LSP diagnostics clean; fresh review `RALPH_REVIEW: PASS`.
**Actionable review:** Re-read `git diff c21666a1eea8cbbf1abcd08aaf23512dec90fb73 HEAD`, inspected every changed file, verified acceptance criteria, reran `uv run pytest` (891 passed, 2 skipped), and checked touched-file LSP diagnostics clean.

## #075 Agent callback env dual-emit + tracker-neutral agent text — 2026-06-17

**What changed:** Added `_tracker_callback_env` so Plane-tracker agents receive tracker-neutral `SYMPHONY_TRACKER_*` aliases alongside the legacy `SYMPHONY_PLANE_*` callback env, and updated agent-visible prompt/schedule wording from Plane-specific comments/tickets to tracker-neutral issue/comment wording.
**Files:** `agent_runner.py`, `prompt_renderer.py`, `schedule.py`, `tests/test_agent_runner.py`, `tests/test_remote_agent.py`, `tests/test_prompt_renderer_podium.py`, `.kanban/issues/075-agent-env-dual-emit-neutral-text.md`.
**Decisions:** Dual-emit is Plane-tracker compatibility only; Podium bindings still receive no tracker callback env, no legacy Plane callback env, and no `plane` helper.
**Conventions established:** New agent-facing callback names should use `SYMPHONY_TRACKER_*`; legacy `SYMPHONY_PLANE_*` remains emitted only where Plane-tracker rollback/back-compat requires it.
**Notes for next iteration:** The `plane` helper / `plane_cli.py` rename remains deferred to Phase 7; issue #076 is independently eligible.
**Verification:** `uv run pytest` (891 passed, 2 skipped); focused agent-runner/remote/prompt/schedule tests passed; `uv run ruff check agent_runner.py prompt_renderer.py schedule.py tests/test_agent_runner.py tests/test_remote_agent.py tests/test_prompt_renderer_podium.py tests/test_schedule.py`; touched-file LSP diagnostics clean; fresh review `RALPH_REVIEW: PASS`.

## #076 Add claude_persist per-binding config flag — 2026-06-17

**What changed:** Added `ProjectBinding.claude_persist` with YAML bool parsing, default `False`, non-bool `ConfigError`, and remote-binding rejection. Passed `persist=binding.claude_persist` into `ClaudeAgentAdapter`, where it is stored but unused for now.
**Files:** `config.py`, `main.py`, `claude_runner.py`, `tests/test_config.py`, `tests/test_main.py`, `.kanban/issues/076-claude-persist-config-flag.md`.
**Decisions:** `claude_persist` is local-only in v1; remote bindings cannot enable it because Claude does not dispatch remotely under ADR-0012.
**Conventions established:** Warm-session flags should parse as strict YAML booleans and stay inert until their behavior slice lands.
**Notes for next iteration:** Issue #077 can consume `binding.claude_persist` from the Claude adapter without changing config parsing; docs/wiki update is intentionally deferred to issue #086.
**Verification:** `uv run pytest tests/test_config.py` (52 passed), `uv run python -m py_compile config.py main.py agent_runner.py`, `uv run pytest tests/test_main.py -q` (13 passed), `uv run pytest -q` (896 passed, 2 skipped), `uv run ruff check config.py main.py claude_runner.py tests/test_config.py tests/test_main.py`, `git diff --check`, touched-file LSP diagnostics clean, and fresh review `RALPH_REVIEW: PASS`.
**Actionable review:** Re-read `git diff b8f470a325c2286ffd3694197789f09ea3ed07e9 HEAD`, inspected every changed file, verified all acceptance criteria, reran the issue verification plus `uv run pytest -q` (896 passed, 2 skipped), checked `ruff`, `git diff --check`, and touched-file LSP diagnostics clean, and added `action_reviewed: 2026-06-17`.


## #077 Split Claude session lifecycle, deterministic socket naming, metadata sidecar — 2026-06-17

**What changed:** Split Claude cleanup into run-scoped and session-scoped teardown, added deterministic persistent tmux socket names, wrote per-session metadata sidecars, and gated session reuse on clean persist-mode success only.
**Files:** `claude_runner.py`, `tests/test_claude_persist.py`, `.kanban/issues/077-claude-session-lifecycle-split-naming-sidecar.md`.
**Decisions:** `persist=False` preserves nonce socket behavior and combined cleanup; `persist=True` keeps per-Run temp dirs while only the tmux session/socket/sidecar survive clean `done` completions.
**Conventions established:** Persistent Claude session state is keyed by `symphony-claude-persist-<binding>-<issue>.sock`, with `<runtime>/claude/<socket-stem>.meta.json` as the reaper transcript mapping.
**Notes for next iteration:** Issue #078 can use the metadata sidecar and deterministic socket as the warm reattach substrate. Issue #079 can build live steer/abort on the extracted Claude poll loop without changing cleanup semantics.
**Verification:** `uv run pytest tests/test_claude_runner.py tests/test_claude_persist.py` (43 passed), `uv run python -m py_compile claude_runner.py`, `uv run ruff check claude_runner.py tests/test_claude_runner.py tests/test_claude_persist.py`, `git diff --check`, touched-file LSP diagnostics clean, fresh review `RALPH_REVIEW: PASS`, and `uv run pytest -q` before final commit.
**Actionable review:** Re-read `git diff 055c44461ec55574c2fba7a16626e9473f340f9e HEAD`, inspected every changed file, verified lifecycle split / persist cleanup / deterministic socket / metadata sidecar acceptance criteria, reran the issue verification plus `uv run pytest -q` (901 passed, 2 skipped), checked ruff, py_compile, `git diff --check`, and touched-file LSP diagnostics clean, and added `action_reviewed: 2026-06-17`.

## #078 Warm reattach to a live Claude session on a second Run — 2026-06-17

**What changed:** Added a live persistent-session reattach path for `claude_persist` Claude runs: live socket/session/server pid reuses the existing tmux session and pastes a fresh per-Run wrapped prompt; stale/dead sockets and failed reattach paste attempts fall back to cold `new-session` without failing the Run.
**Files:** `claude_runner.py`, `tests/test_claude_persist.py`, `.kanban/issues/078-claude-warm-reattach.md`.
**Decisions:** Reattach stays best-effort: pidfile and metadata are rewritten when possible, but any failed precondition or paste race cleans stale session artifacts and uses the existing cold resume/session-id launch path.
**Conventions established:** Warm Claude reattach requires all three liveness checks: deterministic socket exists, `tmux has-session` succeeds, and the tmux server pid is alive.
**Notes for next iteration:** Issue #079 can build steer/abort delivery on top of warm reattach; issue #080 can rely on pidfile/metadata being refreshed during reattach.
**Verification:** `uv run pytest tests/test_claude_persist.py tests/test_claude_runner.py -q` (46 passed), `uv run python -m py_compile claude_runner.py`, `uv run ruff check claude_runner.py tests/test_claude_persist.py tests/test_claude_runner.py`, touched-file LSP diagnostics clean, and fresh review `RALPH_REVIEW: PASS`.
