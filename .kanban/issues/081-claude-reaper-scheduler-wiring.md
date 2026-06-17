---
id: 081
title: Wire the Claude reaper sweep into the scheduler loop
status: blocked
blocked_by: [80]
parent: null
priority: 0
created: 2026-06-17
updated: 2026-06-17
actor: ralph
---

## What to build

Run the reaper sweep once per poll iteration for `claude_persist` bindings, backed by a real single-issue state read, off the event loop. Expose the idle-TTL and max-live cap as configurable settings with safe defaults.

Source: `plans/warm-claude-session-and-send-keys-steer.md` tasks 6.4–6.5.

## What to build (detail)

- In `scheduler.run_loop`, for bindings where `binding.claude_persist` is true, call `sweep_persistent_claude_sessions` each poll iteration via `asyncio.to_thread` (it shells out to tmux; must not block the loop).
- Pass a `get_issue` closure backed by the binding's tracker `adapter`. Confirm the Podium adapter exposes a single-issue fetch returning `state` + `latest_run_state`; if only batch poll exists, fetch the issue row directly. Do NOT infer "terminal" from absence in the active poll (an issue merely not-yet-polled is not terminal).
- Add `idle_ttl_s` (default ~2700s / 45 min) and `max_live` (default 8) to `SymphonyConfig` env with safe defaults.

## Acceptance criteria

- [x] `run_loop` invokes the sweep per poll iteration only for `claude_persist` bindings; non-persist bindings never sweep.
- [x] The sweep runs in `asyncio.to_thread` (does not block the loop) — covered by a scheduler test using a fake sweep/adapter.
- [x] `get_issue` returns real `state` + `latest_run_state`; a not-yet-polled issue is NOT treated as terminal.
- [x] `idle_ttl_s` and `max_live` are configurable with the documented defaults.

## Verification

`uv run pytest tests/test_scheduler.py tests/test_claude_persist.py tests/test_config.py` and `uv run python -m py_compile scheduler/__init__.py config.py`

## Implementation Notes

- Added `SymphonyConfig.claude_persist_idle_ttl_s` (`SYMPHONY_CLAUDE_PERSIST_IDLE_TTL_S`, default `2700`) and `SymphonyConfig.claude_persist_max_live` (`SYMPHONY_CLAUDE_PERSIST_MAX_LIVE`, default `8`).
- Wired `scheduler.run_loop` to sweep persistent Claude sessions once per poll cycle for the scoped `claude_persist` binding only.
- The sweep runs through `asyncio.to_thread`; its `get_issue` closure calls the tracker adapter's single-issue `get_issue`, preserving real `state` and `latest_run_state` instead of inferring terminal state from poll absence.
- Updated the verification command from the removed pre-#071 `scheduler.py` path to the current `scheduler/__init__.py` package entrypoint.
- Fresh review result: `RALPH_REVIEW: PASS`.

## Blocked by

- Blocked by #80 (needs the sweep function).

## Blocker

Auto-parked by review-each: the independent review worker returned no DONE sentinel (timeout, BLOCKED, or FAIL), so completion is unconfirmed. Re-run review or inspect `git diff f5f99c0468bc58e9b23b8b8680bf3c791c4e3842 HEAD` before marking done.
