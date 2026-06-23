# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

## #99 Complete the ClaudeHost seam — 2026-06-23

**What changed:** Completed the additive `ClaudeHost` seam by adding `tmux_argv`, `is_remote`, and `rmtree` across the Protocol, `LocalClaudeHost`, and `SshClaudeHost`.
**Files:** `.gitignore`, `claude_host.py`, `tests/test_claude_host.py`, `.kanban/issues/099-claudehost-seam-completion.md`
**Decisions:** Kept this slice additive; no `claude_runner.py` call sites were rewired.
**Conventions established:** Local host tmux argv preserves the existing `tmux -S <socket>` shape; remote cleanup uses an SSH-wrapped `rm -rf` command with shell-quoted paths.
**Notes for next iteration:** Wire call sites to the host seam in a later slice; this issue only completes the contract.
**Actionable review:** Re-read the base-to-HEAD diff, checked all changed files, verified touched-file LSP diagnostics for `claude_host.py` and `tests/test_claude_host.py`, and reran the issue verification command successfully before adding `action_reviewed`.

## #100 Route runner tmux funnel + session cleanup through the host — 2026-06-23

**What changed:** Routed Claude runner tmux command construction and cleanup through `ClaudeHost` so future remote Claude sessions can keep tmux sockets/temp artifacts on the agent host.
**Files:** `claude_runner.py`, `claude_host.py`, `tests/test_claude_runner.py`, `tests/test_claude_host.py`, `.kanban/issues/100-route-runner-tmux-cleanup-through-host.md`
**Decisions:** Kept `remove_tree` as an optional local-test compatibility injection; normal cleanup now falls back to `host.rmtree`.
**Conventions established:** Any new tmux helper path should accept/thread `host` and call `_tmux(..., host=host)` rather than building tmux argv directly.
**Notes for next iteration:** #101 can add remote launch using the host-threaded tmux/cleanup seam; `LocalClaudeHost.rmtree` now handles socket files as well as temp directories.
**Actionable review:** Fresh reviewer diffed `b176dab83316e93fb55abaf978f11a429f77d6d6..HEAD`, read every changed file, repaired remaining host-backed prompt writes/socket checks plus stale docs, verified touched-file LSP diagnostics clean, and reran the exact verification command successfully.

## #101 Remote-aware Claude launch — 2026-06-23

**What changed:** Added the remote launch branch to `run_claude_agent` while preserving the local launch path.
**Files:** `claude_runner.py`, `tests/test_claude_runner.py`, `.kanban/issues/101-remote-aware-launch-cwd-tempdir-pidfile.md`
**Decisions:** Remote Claude launch sets cwd/env through tmux `-c`/`-e` and only forwards `SYMPHONY_ISSUE_ID`; local launch keeps subprocess `cwd=` and `_claude_env`.
**Conventions established:** Remote Claude temp files and cleanup stay behind `ClaudeHost`; local `/proc` pidfiles are skipped for remote hosts.
**Notes for next iteration:** #102 can build on `host`/`remote_start_dir` to force fresh remote session IDs, disable remote steering, and adjust modal polling.
**Actionable review:** Fresh reviewer diffed `fa2a4d770d1d58bfbfd30d6f9adb69dd3fbdb074..HEAD`, read every changed file, reran the exact verification command successfully, and returned `RALPH_REVIEW: PASS`.
**Actionable review loop:** Re-audited the base diff for #101, checked touched-file LSP diagnostics, reran the exact verification command successfully, and added `action_reviewed`.

## #102 Remote modal handling, fresh session-id, disabled steering — 2026-06-23

**What changed:** Remote Claude runs now handle permission/question modals on every poll, cold-start with a fresh `--session-id`, and ignore queued live steering.
**Files:** `claude_runner.py`, `tests/test_claude_runner.py`, `.kanban/issues/102-remote-modal-continuity-steering.md`
**Decisions:** Remote native resume and live steering stay deferred; remote dispatch always uses a fresh UUID session and drops queued steer records rather than trying to write turns into a remote session.
**Conventions established:** Modal and nudge prompt files are written through `ClaudeHost.write_text`; new remote Claude prompt writes must stay behind the host seam.
**Notes for next iteration:** #103 can open scheduler/config/routing now that remote Claude runner behavior is deterministic for cold-start dispatch.
**Actionable review:** Fresh reviewer diffed `56cae6dbb7a3e1e7268cd73e1d9bbdecc2495429..HEAD`, read every changed file, reran the exact verification command successfully, and returned `RALPH_REVIEW: PASS`.
**Actionable review loop:** Re-audited #102, added explicit remote question-modal host-write coverage, checked touched-file LSP diagnostics, reran the exact verification command successfully, and kept the issue done.

## #103 Relax scheduler gate + resume, config, routing — 2026-06-23

**What changed:** Opened the remote Claude dispatch path across scheduler gating, resume preparation, config validation, routing, and adapter wiring.
**Files:** `scheduler/__init__.py`, `config.py`, `agent_runner.py`, `claude_runner.py`, `main.py`, `tests/test_scheduler.py`, `tests/test_config.py`, `tests/test_agent_runner.py`, `tests/test_remote_agent.py`, `.kanban/issues/103-scheduler-config-routing-wiring.md`
**Decisions:** Remote Claude runs cold-start by design until remote native resume is implemented; the remote host owns Claude probing, tmux, cwd, temp files, and cleanup through `SshClaudeHost`.
**Conventions established:** Remote bindings may now use `default_agent: claude`; `pi_mode: rpc` is only mandatory for remote pi dispatch. `RoutingAgentAdapter` sends remote pi to `remote_adapter` and remote Claude to `claude_adapter`.
**Notes for next iteration:** #104 remains manual/attended live calibration against a disposable remote checkout; Ralph should not automate it.
**Actionable review:** Fresh reviewer diffed `cc584c9211536c6555ce487f18f2fd9bff32a567..HEAD`, read every changed file, reran the exact verification command successfully, and returned `RALPH_REVIEW: PASS`.
