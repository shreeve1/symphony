---
title: "#042 Claude tmux adapter component"
type: analysis
status: promoted
created: 2026-06-13
updated: 2026-06-13
sources:
  - .kanban/issues/042-claude-tmux-adapter.md
  - claude_runner.py
  - tests/test_claude_runner.py
  - docs/adr/0001-claude-via-tmux-send-keys.md
confidence: high
tags: [podium, dispatch, claude, tmux, adapter, ralph]
---

# #042 Claude tmux adapter component

Issue #042 added the Python-native Claude adapter component, but did not wire dispatch routing; #043 remains responsible for selecting it from the scheduler path [source: .kanban/issues/042-claude-tmux-adapter.md]. The existing dispatch gate can still block Claude Issues until routing changes land [source: wiki/analyses/podium-issue-dispatch-contract.md].

## Adapter contract

`claude_runner.py` defines `ClaudeAgentAdapter` and `run_claude_agent(...)` beside the Pi runner instead of folding Claude back into `agent_runner.py` [source: claude_runner.py]. The adapter requires `issue.resolved_model` and raises `AgentRunnerError` before any tmux call if it is empty, so Claude never falls back to `config.pi_model` and never invokes `claude --model ""` [source: claude_runner.py; source: tests/test_claude_runner.py].

Per-run artifacts use the namespace `symphony-claude-<issue.id>-<nonce>` for the tmux socket and session, with prompt/result/done files under a per-run temp directory [source: claude_runner.py]. The nonce is generated per run and tested for variation across repeated runs of the same Issue [source: tests/test_claude_runner.py].

## Tmux lifecycle

Launch runs `tmux -S <socket> new-session -d -s <session> claude --permission-mode bypassPermissions --model <issue.resolved_model>` in the binding repo checkout, or in the created issue worktree when `issue.worktree_active` is true [source: claude_runner.py; source: tests/test_claude_runner.py]. The environment allowlist is limited to `PATH`, `HOME`, `USER`, `LANG`, `TMPDIR`, `XDG_RUNTIME_DIR`, plus `SYMPHONY_ISSUE_ID`; it intentionally omits `TERM`, `NO_COLOR`, Plane variables, and the Pi `plane` helper path [source: claude_runner.py; source: tests/test_claude_runner.py].

The ready poll captures the pane and accepts `bypass permissions on` or `shift+tab to cycle` case-insensitively within a bounded window. A ready timeout returns synthetic exit code `1`, `timed_out=False`, and pane diagnostics prefixed with `claude_ready_timeout` [source: claude_runner.py; source: tests/test_claude_runner.py].

Prompt delivery writes a wrapper to the prompt file, then uses `tmux load-buffer`, `paste-buffer`, and `send-keys Enter` [source: claude_runner.py]. The wrapper tells Claude the run is unattended, nobody can answer questions, the result file must be written first, and the done file touched second; when `preferred_skill` exists it instructs Claude to invoke that skill by name [source: claude_runner.py; source: tests/test_claude_runner.py].

## Completion and result mapping

Completion requires both a done file and a non-empty result file. On success, `stdout` is the result-file content and `stderr` is the ANSI-stripped full pane capture; markerless non-empty result content still exits `0`, preserving scheduler markerless-default behavior [source: claude_runner.py; source: tests/test_claude_runner.py]. Session death without a done file exits `1` with pane-tail diagnostics; done-with-empty/missing result exits `137` as a loud silent-exit analogue; wall-clock timeout kills the session and returns `AgentResult(-1, timed_out=True)` [source: claude_runner.py; source: tests/test_claude_runner.py].

Cleanup is `finally`-guaranteed and idempotent: kill tmux session, unlink socket, remove temp dir, and tolerate repeated cleanup calls [source: claude_runner.py; source: tests/test_claude_runner.py]. Tests also assert no production code invokes `engine.sh` or `claude -p` [source: tests/test_claude_runner.py].

## Verification

Ralph verification for #042 passed `uv run pytest -q` with 679 passed and 1 skipped, `uv run ruff check claude_runner.py tests/test_claude_runner.py`, `git diff --check`, and touched-file LSP diagnostics for Python files [source: .kanban/issues/042-claude-tmux-adapter.md]. Fresh Ralph review returned `RALPH_REVIEW: PASS` for the diff against base commit `2b6c976ef8f87e4c7d8ee3e09b46147a6ca7a5ed` [source: .kanban/issues/042-claude-tmux-adapter.md].
