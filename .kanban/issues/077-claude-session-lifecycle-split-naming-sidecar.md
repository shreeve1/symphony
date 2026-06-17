---
id: 077
title: Split Claude session lifecycle, deterministic socket naming, metadata sidecar
status: done
blocked_by: [76]
parent: null
priority: 0
created: 2026-06-17
---

## What to build

The foundation for warm Claude sessions: separate run-scoped cleanup from session-scoped cleanup, gate session teardown on an explicit `session_reusable` flag, give persistent sessions a deterministic binding-scoped socket name, and write a per-session metadata sidecar the reaper will later read. With `claude_persist=false` the combined cleanup still runs exactly as today (rollback-safe).

Source: `plans/warm-claude-session-and-send-keys-steer.md` tasks 2.1–2.3, 3.1–3.4.

## What to build (detail)

- Refactor `ClaudeRunCleanup` (`claude_runner.py:308`) into `cleanup_run()` (remove `temp_dir` only) and `cleanup_session()` (kill-session, unlink socket, unlink pidfile, unlink the metadata sidecar). Keep a combined `cleanup()` calling both for the non-persist path.
- Track `session_reusable: bool` in `run_claude_agent`, default `False`; set `True` only on the success exit path (clean launch/reattach + normal `done` completion under `persist`). Every error/return path (launch fail `:448`, ready timeout `:468`, session death `:504`, idle-no-completion `:525`, wall-clock `:563`, empty-result `:497`) leaves it `False`.
- In the `finally` (`:565`): ALWAYS `cleanup_run()`; call `cleanup_session()` UNLESS `persist and session_reusable`.
- When `persist`, compute a deterministic, filesystem-safe, binding-scoped socket: `symphony-claude-persist-<sanitized binding>-<sanitized issue>.sock`. Non-persist keeps the existing `symphony-claude-<issue>-<nonce>.sock` exactly. Add pure helpers `persistent_socket_path(binding, issue_id)` and `issue_id_from_persistent_socket(path)`.
- `temp_dir` stays per-Run (fresh `mkdtemp` every Run) even in persist mode.
- Write a metadata sidecar at dispatch under `<runtime>/claude/<socket-stem>.meta.json` carrying `{issue_id, binding, cwd, session_file, session_name}`; `cleanup_session()` unlinks it. This is the authoritative reaper→transcript mapping (handles `worktree_active` cwd).

## Acceptance criteria

- [x] `cleanup_run()` removes only `temp_dir`; `cleanup_session()` kills session + unlinks socket + pidfile + sidecar; both idempotent; combined `cleanup()` preserves current behaviour.
- [x] With `persist=False`, dispatch uses the nonce socket and the `finally` tears the session down on every path (all existing `tests/test_claude_runner.py` pass unchanged).
- [x] With `persist=True`: a clean `done` completion sets `session_reusable=True` and leaves the session+socket+sidecar alive; a launch/ready/idle/timeout failure leaves `session_reusable=False` and tears the session down.
- [x] `persistent_socket_path` is deterministic + sanitized; `issue_id_from_persistent_socket` round-trips a sane id.
- [x] The metadata sidecar is written at dispatch and removed by `cleanup_session()`.

## Verification

`uv run pytest tests/test_claude_runner.py tests/test_claude_persist.py` and `uv run python -m py_compile claude_runner.py`

## Blocked by

- Blocked by #76 (needs `claude_persist` to drive the persist branch).


## Implementation Notes

- Split `ClaudeRunCleanup` into `cleanup_run()`, `cleanup_session()`, and combined `cleanup()`.
- Added persistent Claude socket helpers plus per-session metadata sidecar writes.
- Wired `persist=True` so only clean successful completions leave the tmux session, socket, and metadata sidecar alive; all failure paths still tear down session artifacts.
- Added `tests/test_claude_persist.py` for persist lifecycle and helper coverage.
