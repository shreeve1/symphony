---
id: 102
title: Remote modal handling, fresh session-id, disabled steering
status: done
blocked_by: [101]
parent: 96
priority: 0
created: 2026-06-23
updated: 2026-06-23
actor: ralph
action_reviewed: 2026-06-23
---

## What to build

Make the poll loop behave correctly for a remote run, where the local idle/mtime signal
never fires. Source of truth: `plans/feature-remote-claude-dispatch.md` (Group 4).

- Decouple modal handling from the idle gate: permission/question modal detection must
  run on every poll, not only when `unchanged_polls >= IDLE_POLLS_BEFORE_NUDGE`
  (`claude_runner.py:~1074`). Local behavior unchanged (modals still handled; they just
  no longer require the idle precondition).
- Force a fresh unique `--session-id` per dispatch when `host.is_remote` and skip the
  runner-side local-transcript resume check (`claude_runner.py:800-804`) — remote native
  resume is a deferred v2 item, so remote always cold-starts.
- Disable remote live steering: `_deliver_steer_records` is a no-op when `host.is_remote`.
- Route the modal auto-reply, steer, and nudge prompt-file writes through
  `host.write_text` so a remote run writes to the remote prompt path the remote
  load-buffer actually reads.

## Acceptance criteria

- [x] A permission/question modal is handled on a poll where `unchanged_polls` is below
      the idle threshold.
- [x] Remote dispatch launches with `--session-id` (never `--resume`).
- [x] `_deliver_steer_records` is a no-op when `host.is_remote`.
- [x] Modal/nudge prompt writes go through `host.write_text` (asserted for the remote host).
- [x] Local modal-handling behavior is unchanged (existing tests pass).

## Verification

`.venv/bin/python -m pytest tests/test_claude_runner.py tests/test_claude_persist.py -q && /usr/local/bin/ruff check claude_runner.py`

## Blocked by

- Blocked by #101

## Implementation Notes

- Moved Claude permission/question modal handling out of the idle-only branch so remote runs can clear modals without local transcript mtime.
- Forced remote Claude launches to cold-start with `--session-id` and disabled remote live steering delivery.
- Added remote coverage for early modal handling, fresh session-id despite transcript/resume inputs, and steering no-op; existing local modal tests still pass.
- Verification passed: `.venv/bin/python -m pytest tests/test_claude_runner.py tests/test_claude_persist.py -q && /usr/local/bin/ruff check claude_runner.py`.
- Fresh review passed against `git diff 2c085d9af2c160022d2307aff12efe51bd840391 HEAD`.
