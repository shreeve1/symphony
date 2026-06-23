---
id: 100
title: Route runner tmux funnel + session cleanup through the host
status: pending
blocked_by: [99]
parent: 96
priority: 0
created: 2026-06-23
---

## What to build

Make every tmux call and the session teardown go through the `ClaudeHost` seam so a
remote run's tmux/socket/temp-dir live on the remote, not locally. Source of truth:
`plans/feature-remote-claude-dispatch.md` (Group 2). Local behavior must be byte-for-byte
unchanged (an injected `LocalClaudeHost` reproduces today's argv).

- Rewrite the `_tmux(run_func, socket_path, *args)` funnel (`claude_runner.py`) to build
  its argv from `host.tmux_argv(socket_path, *args)` instead of the hardcoded
  `["tmux","-S",...]`.
- Route `_cleanup_claude_session_artifacts` (kill-session + socket unlink) and
  `ClaudeRunCleanup.cleanup_session` through the host: kill via `host.tmux_argv(...,
  "kill-session", ...)` and remove the socket/temp-dir via `host.rmtree` instead of the
  hardcoded local `shutil.rmtree`.
- `run_claude_agent` already builds `host = LocalClaudeHost(mkdtemp)`; thread it into
  `_tmux` and the cleanup paths.

## Acceptance criteria

- [ ] `_tmux` builds argv via `host.tmux_argv`; with `LocalClaudeHost` the resulting argv
      is identical to today's `["tmux","-S",str(sock),...]`.
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
