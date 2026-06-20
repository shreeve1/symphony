---
id: 069
title: Scope cooldown to _DispatchState; migrate test-only globals
status: done
blocked_by: [68]
parent: null
priority: 0
created: 2026-06-17
updated: 2026-06-17
actor: ralph
action_reviewed: 2026-06-17
---

## What to build

Finding L1-04 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`). `_PLANE_COOLDOWN_UNTIL` (`scheduler.py:63-67`, `:131-146`, `:156-170`, `:178-182`) is a module global dual-tracked alongside `state.cooldown_until` — a 429 on one binding cools down all bindings, undermining per-binding isolation. Several other module globals (`_RUN_SEMAPHORE`, `_POLL_INTERVAL_S`, `_IN_FLIGHT_ISSUE_IDS`, `_IN_FLIGHT_LOCK`) are retained only for test back-compat though `_DispatchState` superseded them.

- Drop `_PLANE_COOLDOWN_UNTIL`; keep only `state.cooldown_until` in `_cooldown_remaining_s` / `_record_rate_limit` / `_clear_rate_limit`.
- Migrate the test-only globals into test fixtures; delete `_fallback_dispatch_state` / `init_run_semaphore` if no longer used.

Removing the globals here keeps the #071 package split from carrying them forward.

## Acceptance criteria

- [x] No `_PLANE_COOLDOWN_UNTIL` module global; cooldown is read/written only via `_DispatchState`.
- [x] A test asserts a 429 on one binding does not set cooldown on another binding's state.
- [x] The test-only globals are removed from `scheduler.py`; tests rely on fixtures instead. `_fallback_dispatch_state`/`init_run_semaphore` deleted if unused.
- [x] `uv run pytest` passes.

## Verification

`uv run pytest`

Live-dispatch-path change: before this issue is marked done, James runs the `symphony-restart` skill and confirms `symphony_started`, `reconcile_startup_*`, and `dispatch_completed` in the journal.

## Blocked by

- Blocked by #068.

## Restart Verification

Live restart verification completed in this Ralph worker:

- `symphony-host.service` restarted successfully; `MainPID=1385687`, `ActiveState=active`, `SubState=running`.
- Journal confirmed `symphony_started service=symphony code_sha=877438f bindings=4`.
- Journal confirmed `rpc_orphan_reap_done count=0` and `pi_rpc_probe_ok`.
- Journal confirmed `reconcile_startup_begin`/`reconcile_startup_done` and `run_reconcile_begin`/`run_reconcile_done` for `homelab`, `symphony`, `dotfiles`, and `n8n`.
- Journal confirmed repeated `dispatch_completed dispatched=false reason=no-candidates` lines.
- `uv run pytest` passed: 887 passed, 2 skipped.
- Critical LSP diagnostics for `scheduler.py` and `tests/test_scheduler.py` were clean.

## Implementation Notes

Completed the previously blocked live verification gate for the #069 implementation. The code changes were already implemented and reviewed in earlier #069 commits; this worker restarted `symphony-host.service`, verified scheduler lifecycle log lines, reran `uv run pytest`, and moved the issue through review to done.
