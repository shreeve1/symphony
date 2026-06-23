# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

## #99 Complete the ClaudeHost seam — 2026-06-23

**What changed:** Completed the additive `ClaudeHost` seam by adding `tmux_argv`, `is_remote`, and `rmtree` across the Protocol, `LocalClaudeHost`, and `SshClaudeHost`.
**Files:** `.gitignore`, `claude_host.py`, `tests/test_claude_host.py`, `.kanban/issues/099-claudehost-seam-completion.md`
**Decisions:** Kept this slice additive; no `claude_runner.py` call sites were rewired.
**Conventions established:** Local host tmux argv preserves the existing `tmux -S <socket>` shape; remote cleanup uses an SSH-wrapped `rm -rf` command with shell-quoted paths.
**Notes for next iteration:** Wire call sites to the host seam in a later slice; this issue only completes the contract.
