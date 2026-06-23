---
id: 101
title: Remote-aware Claude launch (cwd / temp-dir / pidfile)
status: done
blocked_by: [100]
parent: 96
priority: 0
created: 2026-06-23
updated: 2026-06-23
actor: ralph
---

## What to build

Add a remote launch path to `run_claude_agent` while keeping the local launch verbatim.
Source of truth: `plans/feature-remote-claude-dispatch.md` (Group 3). The local path must
keep using the `_claude_env` allowlist — do NOT unify launch on `-c`/`-e`, which would
drop the allowlist and risk leaking local secrets into the remote tmux server env.

- Add `host: ClaudeHost | None = None` (+ a remote start-dir param) to `run_claude_agent`;
  `None` builds `LocalClaudeHost(mkdtemp)` exactly as today.
- Keep the existing local `new-session` launch (with subprocess `cwd=` and
  `env=_claude_env`) unchanged behind `if not host.is_remote`.
- Add an `is_remote` branch that launches via `host.tmux_argv(... "new-session", "-c",
  <remote start-dir>, "-e", "SYMPHONY_ISSUE_ID=...", ...)` — cwd and env set through tmux
  flags (no subprocess `cwd=`/`env=` since tmux runs on the remote), only
  `SYMPHONY_ISSUE_ID` forwarded.
- Temp-dir lifecycle host-aware: use the host's mkdtemp path and `host.rmtree` (no local
  `temp_dir.mkdir` shadow dir for remote).
- Skip the local `/proc` pidfile creation when `host.is_remote` (no local reaper for a
  remote process).

## Acceptance criteria

- [x] Local launch argv + `env=_claude_env` allowlist + subprocess `cwd=` are unchanged
      (existing tests pass).
- [x] Remote launch argv is ssh-wrapped and uses `new-session -c <remote-dir> -e
      SYMPHONY_ISSUE_ID=<id>`, with no subprocess `cwd=`/`env=` and no local secrets.
- [x] No `/proc` pidfile is created on the remote path.
- [x] Remote temp dir is created/removed via the host, not local `mkdir`/`shutil.rmtree`.

## Verification

`.venv/bin/python -m pytest tests/test_claude_runner.py tests/test_claude_persist.py -q && /usr/local/bin/ruff check claude_runner.py`

## Blocked by

- Blocked by #100

## Implementation Notes

- Added injectable `host` and `remote_start_dir` parameters to `run_claude_agent`; the default local path still builds `LocalClaudeHost(mkdtemp)`.
- Kept local Claude launch on subprocess `cwd=` plus `_claude_env`, while remote launch uses tmux `-c` and `-e SYMPHONY_ISSUE_ID=...` with no subprocess `cwd` or `env`.
- Skipped local temp-dir creation and `/proc` pidfile registration for remote hosts; cleanup continues through the host seam.
- Added a remote launch regression test covering ssh-wrapped argv, env/cwd omission, pidfile skip, and host cleanup.
- Verification passed: `.venv/bin/python -m pytest tests/test_claude_runner.py tests/test_claude_persist.py -q && /usr/local/bin/ruff check claude_runner.py`.
