---
id: 079
title: Live steer/abort in the Claude poll loop (generation token)
status: done
blocked_by: [77]
parent: null
priority: 0
created: 2026-06-17
updated: 2026-06-17
actor: ralph
action_reviewed: 2026-06-17
---

## What to build

Make the Claude poll loop read the per-run steer queue and deliver `steer`/`abort` records into the live session via send-keys, keeping every steer-induced turn supervised by a per-steer GENERATION token. Reuses the agent-agnostic queue (`web/api/steer_queue.py`) exactly as the pi RPC adapter does.

Source: `plans/warm-claude-session-and-send-keys-steer.md` tasks 5.1–5.6, 5.4a. (The run-end steer-close guard 5.7 is issue #084; the API allow is #083.)

## What to build (detail)

- Read `run_id = getattr(issue, "active_run_id", "")`; lazily import `web.api.steer_queue` only when set (mirror `agent_runner.py:664`), tolerate import failure (degrade to no-steer).
- Maintain `generation: int` (start 0) with `active_result`/`active_done` = `result.<gen>.txt` / `done.<gen>`; the wrapped prompt names generation 0.
- Each loop iteration: check `active_done.exists()` FIRST, then drain the queue (advance offset like the pi pump).
- On a `steer`: increment generation, compute new `active_result`/`active_done`, `_paste_and_submit` the message + a completion-protocol reminder naming ONLY the new-generation paths, reset idle counters. The loop then watches only the new `active_done`, so the original turn's `done.0` is ignored.
- On an `abort`: send Esc (`tmux send-keys -t <session> Escape`), then the same generation rotation + reminder.
- Idle nudge must name the CURRENT generation: thread `active_result`/`active_done` into `_send_nudge`/`_nudge_text` (`claude_runner.py:718-750`).
- Run-end race: when `active_done` exists, do a FINAL drain; a pending steer rotates the generation and continues; accept completion only when current-gen `active_done` exists AND the final drain found nothing.
- `clear_steer_queue(run_id)` on every adapter exit path.

## Acceptance criteria

- [x] A queued `steer` increments the generation, pastes message + reminder naming the new-gen paths, resets idle counters, loop continues.
- [x] The ORIGINAL turn writing `done.0` after a steer does NOT complete the Run; only the latest-generation `active_done` completes it.
- [x] A queued `abort` sends Esc then rotates the generation.
- [x] An idle nudge after a steer→gen1 names gen1 paths only (never gen0).
- [x] A steer racing turn-end (current `active_done` present + pending steer in final drain) advances the generation rather than completing.
- [x] `clear_steer_queue` is called on every exit path; `persist=False`/no-`run_id` path does no steer polling.

## Verification

`uv run pytest tests/test_claude_persist.py` and `uv run python -m py_compile claude_runner.py`

## Implementation Notes

Implemented Claude live steer polling for `active_run_id` runs with generation-specific `result.<gen>.txt` / `done.<gen>` completion paths. Queued steers and aborts rotate the active generation, paste a fresh completion-protocol reminder naming only the current generation, reset idle supervision, and clear the transient queue on exit. Tests cover steer rotation, stale `done.0` ignore, abort Escape ordering, current-generation idle nudges, final-drain race handling, and queue cleanup.

## Blocked by

- Blocked by #77 (needs the per-Run temp scope and loop structure).
