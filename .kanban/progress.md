# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

# Conventions & Decisions

- Keep Phase 1 architecture-review cleanups behavior-preserving: direct imports, stale-text removal, and docstring corrections only.
- For Podium prompt rendering, apply the skill directive once after branch-specific prompt assembly so resume and non-resume paths stay aligned.

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
