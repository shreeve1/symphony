---
id: 078
title: Warm reattach to a live Claude session on a second Run
status: in-progress
blocked_by: [77]
parent: null
priority: 0
created: 2026-06-17
updated: 2026-06-17
---

## What to build

When `claude_persist` is on and a live persistent session already exists for an issue, a new Run re-attaches to it — skipping `tmux new-session`, the ~30s ready-wait, and the cold `--resume` reload — and just pastes the new prompt. A stale/dead socket falls back to the cold path without ever failing the Run.

Source: `plans/warm-claude-session-and-send-keys-steer.md` tasks 4.1–4.4.

## What to build (detail)

- Before the `tmux new-session` block (`claude_runner.py:424`), when `persist` and `persistent_socket_path` exists with a live session (`has-session` true) AND a live server pid (`_claude_server_pid` + `pid_alive`): take the REATTACH path — skip `new-session`, skip `_wait_until_ready`, skip the `--session-id`/`--resume` flag.
- Reattach delivery: write the per-Run wrapped prompt (`_wrap_prompt`, fresh result/done generation-0 paths) and `_paste_and_submit` into the existing session.
- Reattach-failure fallback: if any precondition fails (socket missing, dead session/pid, paste placeholder never clears) → `cleanup_session()` the stale socket and fall through to the normal cold `new-session` + `--resume` path. A reattach failure NEVER blocks the Run.
- Re-register the pidfile and metadata sidecar on a fresh cold start; on reattach, verify both still match (rewrite if missing).

## Acceptance criteria

- [ ] Live persistent socket present → no `new-session` and no `_wait_until_ready` are invoked; the prompt is pasted into the existing session (assert via recorded fake `run_func` calls).
- [ ] Missing/dead socket under persist → cold `new-session` + `--resume` fallback runs and the Run proceeds (no raised error).
- [ ] On reattach, the pidfile + sidecar are present/matching afterward.
- [ ] `persist=False` path is unchanged (always cold start).

## Verification

`uv run pytest tests/test_claude_persist.py tests/test_claude_runner.py` and `uv run python -m py_compile claude_runner.py`

## Blocked by

- Blocked by #77 (needs deterministic socket naming, sidecar, and the lifecycle split).
