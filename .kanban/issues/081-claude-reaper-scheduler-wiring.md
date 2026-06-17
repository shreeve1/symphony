---
id: 081
title: Wire the Claude reaper sweep into the scheduler loop
status: pending
blocked_by: [80]
parent: null
priority: 0
created: 2026-06-17
---

## What to build

Run the reaper sweep once per poll iteration for `claude_persist` bindings, backed by a real single-issue state read, off the event loop. Expose the idle-TTL and max-live cap as configurable settings with safe defaults.

Source: `plans/warm-claude-session-and-send-keys-steer.md` tasks 6.4–6.5.

## What to build (detail)

- In `scheduler.run_loop`, for bindings where `binding.claude_persist` is true, call `sweep_persistent_claude_sessions` each poll iteration via `asyncio.to_thread` (it shells out to tmux; must not block the loop).
- Pass a `get_issue` closure backed by the binding's tracker `adapter`. Confirm the Podium adapter exposes a single-issue fetch returning `state` + `latest_run_state`; if only batch poll exists, fetch the issue row directly. Do NOT infer "terminal" from absence in the active poll (an issue merely not-yet-polled is not terminal).
- Add `idle_ttl_s` (default ~2700s / 45 min) and `max_live` (default 8) to `SymphonyConfig` env with safe defaults.

## Acceptance criteria

- [ ] `run_loop` invokes the sweep per poll iteration only for `claude_persist` bindings; non-persist bindings never sweep.
- [ ] The sweep runs in `asyncio.to_thread` (does not block the loop) — covered by a scheduler test using a fake sweep/adapter.
- [ ] `get_issue` returns real `state` + `latest_run_state`; a not-yet-polled issue is NOT treated as terminal.
- [ ] `idle_ttl_s` and `max_live` are configurable with the documented defaults.

## Verification

`uv run pytest tests/test_scheduler.py tests/test_claude_persist.py tests/test_config.py` and `uv run python -m py_compile scheduler.py config.py`

## Blocked by

- Blocked by #80 (needs the sweep function).
