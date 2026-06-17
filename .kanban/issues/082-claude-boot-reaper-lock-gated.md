---
id: 082
title: Lock-gated boot reaping of persistent Claude sockets
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

Fix the cross-restart leak: a detached tmux server survives the scheduler dying, and its still-valid pidfile makes the existing boot reaper SKIP it, so warm persist sockets would accumulate across restarts. At boot, kill persist sockets bypassing the pidfile guard — but ONLY when single-instance lock ownership is confirmed; otherwise fall back to the pid/start-time guard (accept the leak over killing a live peer scheduler).

Source: `plans/warm-claude-session-and-send-keys-steer.md` tasks 6.6–6.7.

## What to build (detail)

- Change `reap_orphan_claude_sockets` (`claude_runner.py:118`) into one function taking `lock_confirmed: bool`: with the lock confirmed, kill any `symphony-claude-persist-*.sock` bypassing the pidfile guard; without it, apply the existing pid/start-time guard to persist sockets too. Non-persist nonce sockets keep the existing guarded behaviour always.
- At the `main.py:191` entrypoint, verify the single-instance lock (`config.py` `SYMPHONY_LOCK_PATH`) is acquired and held BEFORE the reap call, and pass `lock_confirmed` accordingly. If ownership cannot be confirmed at the reap point, pass `False`.
- Document that warm-reattach is within-scheduler-lifetime only (restart = cold `--resume`).

## Acceptance criteria

- [x] With `lock_confirmed=True`, a persist-named socket WITH a live matching pidfile is still reaped at boot (C2 regression).
- [x] With `lock_confirmed=False`, the same socket is KEPT (pid-guard fallback), so a concurrent peer scheduler's warm sessions are never killed (round-2 W1 regression).
- [x] Non-persist nonce sockets keep the existing guarded reaping in both cases.
- [x] The entrypoint passes a truthful `lock_confirmed` derived from actual lock ownership.

## Verification

`uv run pytest tests/test_claude_runner.py tests/test_claude_persist.py` and `uv run python -m py_compile claude_runner.py main.py`

## Blocked by

- Blocked by #77 (needs persist socket naming).

## Implementation Notes

- Added `lock_confirmed` to `reap_orphan_claude_sockets`; persistent sockets bypass the live-pid guard only when boot lock ownership is confirmed.
- Added startup lock acquisition in `run_bindings_loop` and pass-through to the Claude boot reaper.
- Documented warm Claude sessions as scheduler-lifetime only: restart forces cold resume from transcript.
