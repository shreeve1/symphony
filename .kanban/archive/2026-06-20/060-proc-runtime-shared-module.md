---
id: 060
title: proc_runtime.py shared process-runtime module
status: done
blocked_by: []
updated: 2026-06-17
actor: ralph
parent: null
priority: 0
created: 2026-06-17
---

## What to build

Finding L2-03 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`). `claude_runner.py:17-26` imports the underscore-private `_pid_alive`, `_pid_start_time`, `_strip_ansi`, `_DEFAULT_RUNTIME_DIR`, `RPC_RUNTIME_DIR_ENV` cross-module from `agent_runner`. Move the genuinely-shared process-reap primitives, ANSI stripping, and runtime-dir constants into a new neutral module `proc_runtime.py` with public names; both runners import from it.

No behavior change — pure relocation + de-privatization.

## Acceptance criteria

- [x] New `proc_runtime.py` defines public-named `pid_alive`, `pid_start_time`, `strip_ansi` and the runtime-dir constants (no leading underscore on the shared API).
- [x] `claude_runner.py` imports these from `proc_runtime`, not via underscore-private names from `agent_runner`.
- [x] `agent_runner.py` sources the same helpers from `proc_runtime` (re-export or direct import); no duplicate definitions remain.
- [x] Import graph stays acyclic.
- [x] `uv run pytest` passes.

## Verification

`uv run pytest`

## Blocked by

None — can start immediately.

## Implementation Notes

Added `proc_runtime.py` as the neutral home for process-liveness helpers, process start-time lookup, ANSI stripping, and shared runtime-dir constants. Updated `agent_runner.py` and `claude_runner.py` to import the public helpers from that module, and adjusted the Claude runner test monkeypatch to the new public name.

Verification: `uv run pytest` passed (878 passed, 2 skipped). `uv run ruff check proc_runtime.py agent_runner.py claude_runner.py tests/test_claude_runner.py` passed. Touched-file LSP reported stale `reportMissingImports` for newly-created `proc_runtime`; runtime import smoke (`uv run python -c 'import agent_runner, claude_runner, proc_runtime'`) and full pytest both resolved it successfully.
