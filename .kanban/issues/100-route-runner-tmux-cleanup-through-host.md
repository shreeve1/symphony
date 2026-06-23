---
id: 100
title: Route runner tmux funnel + session cleanup through the host
status: in-progress
blocked_by: [99]
parent: 96
priority: 0
created: 2026-06-23
updated: 2026-06-23
actor: ralph
---

## What to build

Make every tmux call and the session teardown go through the `ClaudeHost` seam so a
remote run's tmux/socket/temp-dir live on the remote, not locally. Source of truth:
`plans/feature-remote-claude-dispatch.md` (Group 2). Local behavior must be byte-for-byte
unchanged (an injected `LocalClaudeHost` reproduces today's argv).

- Rewrite the `_tmux(run_func, socket_path, *args)` funnel (`claude_runner.py`) to
  `_tmux(host, run_func, socket_path, *args)`, building its argv from
  `host.tmux_argv(socket_path, *args)` instead of the hardcoded `["tmux","-S",...]`.
- **Thread `host` through EVERY `_tmux` caller — with NO defaulted `host` parameter.** A
  hidden `LocalClaudeHost` default would compile, pass the local tests, and then silently
  run tmux on the scheduler host for a remote binding (broken remote dispatch that no unit
  test catches). The callers/wrappers that must forward `host`: `_capture_pane_full`,
  `_capture_pane_tail`, `_paste_and_submit`, `_send_nudge`, `_send_down`, `_session_alive`,
  and the direct `_tmux(...)` calls (Escape/Enter send-keys, kill, has-session). Their own
  callers in `_poll_claude_until_done` / `_wait_until_ready` / `run_claude_agent` pass the
  run's `host`. (Plan task 2.2.)
- Route `_cleanup_claude_session_artifacts` (kill-session + socket unlink) and
  `ClaudeRunCleanup.cleanup_session` through the host: kill via `host.tmux_argv(...,
  "kill-session", ...)` and remove the socket/temp-dir via `host.rmtree` instead of the
  hardcoded local `shutil.rmtree`.
- Make the socket-existence checks host-aware: `socket_path.exists()` in the reaper
  (`claude_runner.py:377`) and the persist branch (`:854`) use `host.exists` for remote.
  (Plan task 2.4. The `:854` check is persist-gated and remote forbids persist, so it is
  defensive, but `:377` is on a live cleanup path.)
- `run_claude_agent` already builds `host = LocalClaudeHost(mkdtemp)`; thread it into
  `_tmux` and the cleanup paths.

## Acceptance criteria

- [ ] `_tmux` builds argv via `host.tmux_argv`; with `LocalClaudeHost` the resulting argv
      is identical to today's `["tmux","-S",str(sock),...]`.
- [ ] `_tmux` takes `host` as a required (non-defaulted) parameter, and every wrapper
      (`_capture_pane_full/_tail`, `_paste_and_submit`, `_send_nudge`, `_send_down`,
      `_session_alive`) forwards an explicit `host` — no `host=` default anywhere.
- [ ] A remote (fake `SshClaudeHost`) run's `has-session` liveness check and pane captures
      go through `host.tmux_argv` (run on the remote), not the local host.
- [ ] Cleanup kills the session via `host.tmux_argv(...,"kill-session",...)` and removes
      artifacts via `host.rmtree` (no direct `shutil.rmtree` / hardcoded `tmux` left in
      the cleanup path).
- [ ] Existing `tests/test_claude_runner.py` + `tests/test_claude_persist.py` pass
      unchanged in behavior (TmuxFake + injected LocalClaudeHost).
- [ ] New test: a remote (fake `SshClaudeHost`) run kills the session and rmtrees via
      the host, not locally.

## Verification

`.venv/bin/python -m pytest tests/test_claude_runner.py tests/test_claude_persist.py tests/test_claude_host.py -q && /usr/local/bin/ruff check claude_runner.py claude_host.py`

## Blocked by

- Blocked by #99
