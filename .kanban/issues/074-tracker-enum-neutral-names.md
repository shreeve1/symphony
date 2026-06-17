---
id: 074
title: Tracker enum neutral names with Plane* aliases
status: pending
blocked_by: [64]
parent: null
priority: 0
created: 2026-06-17
---

## What to build

Phase 6 / finding L3-04 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`). Generic role-projection vocabulary in `tracker_contract.py` carries a Plane-specific prefix though Podium depends on it too: `PlaneState` (`:48`), `PlaneLabel` (`:58`), `PlaneUserMapping` (`:98`), `PlaneContract = TrackerContract` (`:262`); reused by Podium (`tracker_podium.py:25-33`, `PODIUM_CONTRACT`).

Rename the canonical names to `TrackerState` / `TrackerLabel` / `TrackerUserMapping` (and keep the existing `TrackerContract`); keep `PlaneState = TrackerState` style compat aliases for one release so existing importers keep working.

## Acceptance criteria

- [ ] Canonical `TrackerState` / `TrackerLabel` / `TrackerUserMapping` defined in `tracker_contract.py`.
- [ ] `PlaneState` / `PlaneLabel` / `PlaneUserMapping` / `PlaneContract` retained as compat aliases pointing at the canonical names.
- [ ] `PODIUM_CONTRACT` and all importers resolve via either the canonical or alias name.
- [ ] `uv run pytest` passes.

## Verification

`uv run pytest`

## Blocked by

- Blocked by #064 (tracker vocabulary home established first so the renames are coordinated).
