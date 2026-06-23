---
id: 102
title: Remote modal handling, fresh session-id, disabled steering
status: in-progress
blocked_by: [101]
parent: 96
priority: 0
created: 2026-06-23
updated: 2026-06-23
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

- [ ] A permission/question modal is handled on a poll where `unchanged_polls` is below
      the idle threshold.
- [ ] Remote dispatch launches with `--session-id` (never `--resume`).
- [ ] `_deliver_steer_records` is a no-op when `host.is_remote`.
- [ ] Modal/nudge prompt writes go through `host.write_text` (asserted for the remote host).
- [ ] Local modal-handling behavior is unchanged (existing tests pass).

## Verification

`.venv/bin/python -m pytest tests/test_claude_runner.py tests/test_claude_persist.py -q && /usr/local/bin/ruff check claude_runner.py`

## Blocked by

- Blocked by #101
