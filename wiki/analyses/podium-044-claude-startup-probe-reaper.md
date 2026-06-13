---
title: "#044 Claude startup probe and orphan socket reaper"
type: analysis
status: promoted
created: 2026-06-13
updated: 2026-06-13
sources:
  - .kanban/issues/044-claude-startup-probe-and-socket-reaper.md
  - claude_runner.py
  - scheduler.py
  - main.py
  - tests/test_claude_runner.py
  - tests/test_dispatch_gate.py
  - tests/test_main.py
confidence: high
tags: [podium, dispatch, claude, startup, tmux, ralph]
---

# #044 Claude startup probe and orphan socket reaper

Issue #044 hardens the now-wired Claude engine without making Claude availability a hard scheduler dependency [source: .kanban/issues/044-claude-startup-probe-and-socket-reaper.md]. `verify_claude_support(...)` checks for `tmux`, checks for the `claude` binary, and runs only `claude --version` with a bounded timeout; it never launches a live Claude session and never spends model tokens [source: claude_runner.py].

## Fail-soft probe state

Claude probe failures are recorded in module state via `set_claude_probe_failure_reason(...)` / `claude_probe_failure_reason()` and logged as `claude_probe_failed reason=...` [source: claude_runner.py]. Failure paths cover missing binaries, `OSError`, non-zero `claude --version`, and timeout; all return without raising so Symphony can keep booting for Pi-only work [source: claude_runner.py; source: tests/test_claude_runner.py]. Successful probe clears any prior failure and logs `claude_probe_ok` [source: claude_runner.py; source: tests/test_claude_runner.py].

The dispatch gate checks the probe state only for resolved `agent == "claude"`. If a startup probe failed, Claude Issues block with `Dispatch blocked: claude engine probe failed at startup: <reason>. Fix the install and restart.`, while Pi dispatch remains unaffected [source: scheduler.py; source: tests/test_dispatch_gate.py]. This refines #043: Claude routing exists, but broken local Claude support disables only Claude dispatch until the install is fixed and the service restarts [source: wiki/analyses/podium-043-claude-dispatch-routing.md; source: scheduler.py].

## Orphan socket reaper

`reap_orphan_claude_sockets(...)` scans `/tmp/symphony-claude-*.sock`, runs `tmux -S <socket> kill-server` for each survivor, ignores kill failures, unlinks the socket, logs `claude_socket_reaped path=...` per socket, and logs `claude_socket_reap_done count=<n>` at the end [source: claude_runner.py]. Tests cover two stale sockets, zero sockets, and a kill failure on one socket not aborting the rest [source: tests/test_claude_runner.py].

`main.run_bindings_loop(...)` runs the socket reaper and then the Claude probe exactly once globally before building per-binding runtimes and before the per-binding startup reconcile loop [source: main.py]. The multi-binding regression test asserts one reaper call and one probe call with two configured bindings [source: tests/test_main.py].

## Verification

Ralph verification for #044 passed `git diff --check`, secret-pattern diff scan, touched-file LSP diagnostics with no errors, full `uv run pytest` (690 passed, 1 skipped), `uv run pytest -q` (690 passed, 1 skipped), and fresh read-only Ralph review against base commit `76c07f055d2d87ebbc4a967a3041e1297aa04401` with result `RALPH_REVIEW: PASS` [source: .kanban/issues/044-claude-startup-probe-and-socket-reaper.md].
