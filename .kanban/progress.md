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
