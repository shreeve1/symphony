---
id: 065
title: Extract _probe_binding from the runtime factory
status: in-progress
blocked_by: []
parent: null
priority: 0
created: 2026-06-17
updated: 2026-06-17
actor: ralph
---

## What to build

Finding L0-03 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`). `_build_binding_runtime` (`main.py:92-179`) interleaves side-effecting startup verification (subprocess pi probe, SSH reachability check, warning/info logging — lines 101-145) with pure object construction.

Extract the probe block into a named `_probe_binding(config, binding)` helper called before construction; `_build_binding_runtime` becomes pure wiring. Prerequisite for promoting the factory to a public API (#066).

## Acceptance criteria

- [ ] `_probe_binding(config, binding)` exists and owns the pi-probe + SSH-reachability + logging side effects.
- [ ] `_build_binding_runtime` contains no startup-verification side effects — pure adapter/router assembly only.
- [ ] `_probe_binding` is invoked before runtime construction in the call path.
- [ ] Behavior unchanged; `uv run pytest` passes.

## Verification

`uv run pytest`

## Blocked by

None — can start immediately.
