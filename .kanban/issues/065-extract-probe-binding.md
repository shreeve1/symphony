---
id: 065
title: Extract _probe_binding from the runtime factory
status: done
blocked_by: []
parent: null
priority: 0
created: 2026-06-17
updated: 2026-06-17
action_reviewed: 2026-06-17
actor: ralph
---

## What to build

Finding L0-03 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`). `_build_binding_runtime` (`main.py:92-179`) interleaves side-effecting startup verification (subprocess pi probe, SSH reachability check, warning/info logging — lines 101-145) with pure object construction.

Extract the probe block into a named `_probe_binding(config, binding)` helper called before construction; `_build_binding_runtime` becomes pure wiring. Prerequisite for promoting the factory to a public API (#066).

## Acceptance criteria

- [x] `_probe_binding(config, binding)` exists and owns the pi-probe + SSH-reachability + logging side effects.
- [x] `_build_binding_runtime` contains no startup-verification side effects — pure adapter/router assembly only.
- [x] `_probe_binding` is invoked before runtime construction in the call path.
- [x] Behavior unchanged; `uv run pytest` passes.

## Verification

`uv run pytest`

## Blocked by

None — can start immediately.

## Implementation Notes

Extracted startup probe side effects from `_build_binding_runtime` into `_probe_binding(config, binding)`. `run_bindings_loop` now probes each binding before constructing its runtime, while `_build_binding_runtime` only assembles tracker, agent, transport, and routing adapters. Updated `tests/test_main.py` to cover the new call order and probe helper behavior.

Verification: `uv run pytest` passed (884 passed, 2 skipped). Fresh review diffed `55fcd52dde913b3b5b41d6a3aabadf993c6475d6 HEAD` and returned `RALPH_REVIEW: PASS`.
