---
id: 059
title: Phase 1 — foundation cleanups
status: done
blocked_by: []
parent: null
priority: 0
created: 2026-06-17
updated: 2026-06-17
actor: ralph
---

## What to build

Phase 1 of the root-scheduler architecture review: eight independent, test-pinned micro-edits. Source: `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md` (findings L0-04, L0-05, L1-05, L1-07, L2-06, L4-02, L7-01, L7-04). No new modules, no behavior change — dead-code/constant deletion, import hoists, docstring corrections.

- **L0-04** — `main.py`: hoist `from model_catalog import load_models, resolve_model` to module top. Keep the lazy `import_module("tracker_podium")` but add a one-line comment: it defers the `web.api.db` coupling for plane-only bindings.
- **L0-05** — reword stale docstrings. `__init__.py:1` (drops "Plane … skeleton") and `main.py:1` (drops "Container entrypoint" — service is host-native `symphony-host.service`). Both become host-native, tracker-agnostic one-liners.
- **L1-05** — `scheduler.py`: replace the `import_module("context_compaction")` + `vars(compaction)[...]` reflection (`:768,770,787,796`) with a normal `from context_compaction import ContextCompactionError, estimate_tokens, maybe_compact` and direct calls.
- **L1-07** — `scheduler.py:2183`: drop the unused `config: SymphonyConfig | None = None` parameter from `reconcile_stale_running`; update any test call passing it.
- **L2-06** — `claude_runner.py:35`: delete the dead `READY_PATTERN` constant; leave the inline `_ready_pattern_seen` substring check untouched.
- **L4-02** — `prompt_renderer.py:316-335`: hoist the duplicated `if tracker_kind == "podium"` skill-directive prepend to a single application before the final return.
- **L7-01** — `notifier.py:48`: add a docstring to `send_sync` noting it has no current production caller (deliberate sync-context primitive paired with the async `send`).
- **L7-04** — `code_version.py:3`: reword the docstring to "startup logging + Run-record provenance"; drop the removed Plane-claim-comment reference.

## Acceptance criteria

- [x] `main.py` imports `model_catalog` at module top; the `import_module("tracker_podium")` line is retained with a one-line comment explaining the deferred `web.api.db` edge.
- [x] `__init__.py` and `main.py` module docstrings no longer contain "Plane", "skeleton", or "Container entrypoint"; both read host-native / tracker-agnostic.
- [x] `scheduler.py` contains no `vars(compaction)` or `import_module("context_compaction")`; `maybe_compact`/`estimate_tokens`/`ContextCompactionError` are reached via a normal top-level import.
- [x] `reconcile_stale_running` signature no longer has a `config` parameter.
- [x] `claude_runner.py` no longer defines `READY_PATTERN`; `_ready_pattern_seen` behavior is unchanged.
- [x] `prompt_renderer.py` applies the podium skill-directive prepend exactly once (not in both return branches).
- [x] `notifier.send_sync` has a docstring noting no current production caller.
- [x] `code_version.py` docstring no longer references Plane claim comments.
- [x] `uv run pytest` passes.

## Verification

`uv run pytest`

## Implementation Notes

- Hoisted `model_catalog` imports in `main.py` and documented the lazy Podium adapter import.
- Replaced scheduler context-compaction reflection with direct imports/calls and removed the unused `reconcile_stale_running` config parameter.
- Removed stale/dead text and constants in `__init__.py`, `main.py`, `claude_runner.py`, `code_version.py`, and `notifier.py`.
- Consolidated Podium skill-directive prepending in `prompt_renderer.py` to one return-path application.
- Verified with LSP diagnostics for touched Python files and `uv run pytest` (878 passed, 2 skipped).
- Fresh review result: `RALPH_REVIEW: PASS`.

## Blocked by

None — can start immediately.
