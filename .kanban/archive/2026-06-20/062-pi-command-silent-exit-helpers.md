---
id: 062
title: Extract pi-command + silent-exit helpers
status: done
blocked_by: []
parent: null
priority: 0
created: 2026-06-17
updated: 2026-06-17
actor: ralph
---

## What to build

Finding L2-01 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`). The pi command list is assembled in three places (`agent_runner.py:296-304`, `:464-472`, `:142-151`) and the "clean exit + empty output → treat as 137 failure" guard is copy-pasted in the local and remote paths (`:339-346` ≈ `:540-547`).

Extract `_build_pi_command` and `_silent_exit_result` in `agent_runner.py`. Pass `pi_bin`/`skill_source` as arguments so the basename-vs-abspath and remote-skill-skip divergences stay at the call site.

## Acceptance criteria

- [x] `_build_pi_command` exists; the three command-assembly sites use it.
- [x] `_silent_exit_result` exists; the two silent-exit guards use it.
- [x] Basename-vs-abspath and remote-skill-skip divergence preserved (passed as args, not hard-coded in the helper).
- [x] Behavior unchanged; `uv run pytest` passes.

## Verification

`uv run pytest`

## Blocked by

None — can start immediately.

## Implementation Notes

Extracted `_build_pi_command` and `_silent_exit_result` in `agent_runner.py`, repointed local one-shot, remote one-shot, RPC, and probe command construction through the helper, and added focused tests for command construction plus silent-exit handling. Verified with `uv run pytest` and fresh Ralph review.
