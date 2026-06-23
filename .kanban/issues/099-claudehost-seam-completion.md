---
id: 99
title: Complete the ClaudeHost seam (tmux_argv / is_remote / rmtree)
status: in-progress
blocked_by: []
parent: 96
priority: 0
created: 2026-06-23
updated: 2026-06-23
actor: ralph
---

## What to build

Finish the `ClaudeHost` abstraction so the runner can be made host-aware without
behavior change. Source of truth: `plans/feature-remote-claude-dispatch.md` (Group 1).

- Add to the `ClaudeHost` Protocol and to `LocalClaudeHost` (`claude_host.py`):
  - `tmux_argv(socket_path, *args) -> list[str]` — returns the argv to run a tmux
    subcommand. `LocalClaudeHost` returns `["tmux", "-S", str(socket_path), *args]`
    (today's exact shape). `SshClaudeHost.tmux_argv` already exists; this makes the
    Protocol total.
  - `is_remote: bool` property — `False` for local, `True` for `SshClaudeHost`.
  - `rmtree(path)` — `LocalClaudeHost` calls `shutil.rmtree(path, ignore_errors=True)`;
    `SshClaudeHost` runs a remote `rm -rf`.
- Purely additive. No call sites change yet, so the full existing suite stays green.

## Acceptance criteria

- [ ] `ClaudeHost` Protocol declares `tmux_argv`, `is_remote`, `rmtree`.
- [ ] `LocalClaudeHost.tmux_argv(sock, "new-session", ...)` == `["tmux","-S",str(sock),"new-session",...]`.
- [ ] `LocalClaudeHost.is_remote is False`; `SshClaudeHost.is_remote is True`.
- [ ] `SshClaudeHost.rmtree` produces an ssh-wrapped `rm -rf <path>` argv (asserted, not executed).
- [ ] No behavior change to existing runner/persist tests.

## Verification

`.venv/bin/python -m pytest tests/test_claude_host.py tests/test_claude_runner.py tests/test_claude_persist.py -q && /usr/local/bin/ruff check claude_host.py`

## Blocked by

None — can start immediately.
