# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

## #99 Complete the ClaudeHost seam — 2026-06-23

**What changed:** Completed the additive `ClaudeHost` seam by adding `tmux_argv`, `is_remote`, and `rmtree` across the Protocol, `LocalClaudeHost`, and `SshClaudeHost`.
**Files:** `.gitignore`, `claude_host.py`, `tests/test_claude_host.py`, `.kanban/issues/099-claudehost-seam-completion.md`
**Decisions:** Kept this slice additive; no `claude_runner.py` call sites were rewired.
**Conventions established:** Local host tmux argv preserves the existing `tmux -S <socket>` shape; remote cleanup uses an SSH-wrapped `rm -rf` command with shell-quoted paths.
**Notes for next iteration:** Wire call sites to the host seam in a later slice; this issue only completes the contract.
**Actionable review:** Re-read the base-to-HEAD diff, checked all changed files, verified touched-file LSP diagnostics for `claude_host.py` and `tests/test_claude_host.py`, and reran the issue verification command successfully before adding `action_reviewed`.

## #100 Route runner tmux funnel + cleanup through ClaudeHost — 2026-06-23

**What changed:** Threaded explicit `ClaudeHost` arguments through Claude tmux helpers and routed cleanup/session checks through host operations.
**Files:** `claude_runner.py`, `claude_host.py`, `tests/test_claude_runner.py`, `tests/test_claude_persist.py`, `.kanban/issues/100-route-runner-tmux-cleanup-through-host.md`
**Decisions:** Kept local launch behavior byte-identical by preserving `LocalClaudeHost.tmux_argv`; kept the runner's test cleanup hook behind an injected local host.
**Conventions established:** Host-aware Claude runner helpers take `host` as a required positional argument, never a defaulted local host.
**Notes for next iteration:** #101 can add the remote launch path on top of this seam; persistent PID sidecars still describe local process ownership only.
**Actionable review:** Fresh reviewer inspected `git diff b76db6cef32e4504cc9eb32d939f5b56d4702ad7 HEAD`, read changed files, reran the issue verification command, and returned `RALPH_REVIEW: PASS`.
