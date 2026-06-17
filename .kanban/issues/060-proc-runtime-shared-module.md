---
id: 060
title: proc_runtime.py shared process-runtime module
status: in-progress
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

- [ ] New `proc_runtime.py` defines public-named `pid_alive`, `pid_start_time`, `strip_ansi` and the runtime-dir constants (no leading underscore on the shared API).
- [ ] `claude_runner.py` imports these from `proc_runtime`, not via underscore-private names from `agent_runner`.
- [ ] `agent_runner.py` sources the same helpers from `proc_runtime` (re-export or direct import); no duplicate definitions remain.
- [ ] Import graph stays acyclic.
- [ ] `uv run pytest` passes.

## Verification

`uv run pytest`

## Blocked by

None — can start immediately.
