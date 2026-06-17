---
id: 069
title: Scope cooldown to _DispatchState; migrate test-only globals
status: in-progress
blocked_by: [68]
parent: null
priority: 0
created: 2026-06-17
updated: 2026-06-17
actor: ralph
---

## What to build

Finding L1-04 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`). `_PLANE_COOLDOWN_UNTIL` (`scheduler.py:63-67`, `:131-146`, `:156-170`, `:178-182`) is a module global dual-tracked alongside `state.cooldown_until` — a 429 on one binding cools down all bindings, undermining per-binding isolation. Several other module globals (`_RUN_SEMAPHORE`, `_POLL_INTERVAL_S`, `_IN_FLIGHT_ISSUE_IDS`, `_IN_FLIGHT_LOCK`) are retained only for test back-compat though `_DispatchState` superseded them.

- Drop `_PLANE_COOLDOWN_UNTIL`; keep only `state.cooldown_until` in `_cooldown_remaining_s` / `_record_rate_limit` / `_clear_rate_limit`.
- Migrate the test-only globals into test fixtures; delete `_fallback_dispatch_state` / `init_run_semaphore` if no longer used.

Removing the globals here keeps the #071 package split from carrying them forward.

## Acceptance criteria

- [ ] No `_PLANE_COOLDOWN_UNTIL` module global; cooldown is read/written only via `_DispatchState`.
- [ ] A test asserts a 429 on one binding does not set cooldown on another binding's state.
- [ ] The test-only globals are removed from `scheduler.py`; tests rely on fixtures instead. `_fallback_dispatch_state`/`init_run_semaphore` deleted if unused.
- [ ] `uv run pytest` passes.

## Verification

`uv run pytest`

Live-dispatch-path change: before this issue is marked done, James runs the `symphony-restart` skill and confirms `symphony_started`, `reconcile_startup_*`, and `dispatch_completed` in the journal.

## Blocked by

- Blocked by #068.
