---
id: 074
title: Tracker enum neutral names with Plane* aliases
status: done
blocked_by: [64]
parent: null
priority: 0
created: 2026-06-17
updated: 2026-06-17
actor: ralph
action_reviewed: 2026-06-17
---

## What to build

Phase 6 / finding L3-04 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`). Generic role-projection vocabulary in `tracker_contract.py` carries a Plane-specific prefix though Podium depends on it too: `PlaneState` (`:48`), `PlaneLabel` (`:58`), `PlaneUserMapping` (`:98`), `PlaneContract = TrackerContract` (`:262`); reused by Podium (`tracker_podium.py:25-33`, `PODIUM_CONTRACT`).

Rename the canonical names to `TrackerState` / `TrackerLabel` / `TrackerUserMapping` (and keep the existing `TrackerContract`); keep `PlaneState = TrackerState` style compat aliases for one release so existing importers keep working.

## Acceptance criteria

- [x] Canonical `TrackerState` / `TrackerLabel` / `TrackerUserMapping` defined in `tracker_contract.py`.
- [x] `PlaneState` / `PlaneLabel` / `PlaneUserMapping` / `PlaneContract` retained as compat aliases pointing at the canonical names.
- [x] `PODIUM_CONTRACT` and all importers resolve via either the canonical or alias name.
- [x] `uv run pytest` passes.

## Verification

`uv run pytest`

## Blocked by

- Blocked by #064 (tracker vocabulary home established first so the renames are coordinated).

## Implementation Notes

Added canonical `TrackerState`, `TrackerLabel`, and `TrackerUserMapping` names in `tracker_contract.py`, with `PlaneState`, `PlaneLabel`, `PlaneUserMapping`, and `PlaneContract` retained as compatibility aliases. Repointed tracker adapter, Podium tracker, and config annotations to the canonical names while leaving legacy importers on aliases. Added focused contract tests for canonical exports and alias identity.
