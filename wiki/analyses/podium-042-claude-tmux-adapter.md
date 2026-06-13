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

Issue #042 added the Python-native Claude adapter component, but did not wire dispatch routing; #043 later made `RoutingAgentAdapter` select it from the scheduler path [source: .kanban/issues/042-claude-tmux-adapter.md] [source: wiki/analyses/podium-043-claude-dispatch-routing.md]. Before #043, the dispatch gate still blocked Claude Issues [source: wiki/analyses/podium-issue-dispatch-contract.md].

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

## Live paste/submit + result races (2026-06-13)

The first live Claude dispatches (issues 6, 7 — see `wiki/raw/sessions/2026-06-13-claude-path-046-e2e-and-fixes.md`) exposed two timing races in the send-keys flow; the #046 contract itself is sound on Claude (a manual repro wrote a correct verbatim `SYMPHONY_SUMMARY` block, and Run rows stored `provider=''` / bare `claude-opus-4-8` per C-0152):

- **Paste/Enter race (root cause).** `paste-buffer` was followed by an immediate `send-keys Enter`; for the full ~217-line rendered prompt the Enter is absorbed into the paste and the prompt is never submitted (pane shows `❯ [Pasted text …]`), so the run idles to the 60-min timeout [source: claude_runner.py]. Fix: `_paste_and_submit` settles `PASTE_SETTLE_SECONDS=1.0` after paste, then re-sends Enter up to `SUBMIT_RETRY_ATTEMPTS=3` while `_paste_pending` still sees the placeholder.
- **Done-before-result race.** Claude touches the done file a beat before the result write is visible; the done-but-empty branch returned an instant `137` with no grace and no pane capture. Fix: `_read_result_with_grace` re-polls the result up to `RESULT_GRACE_SECONDS=3.0` (iteration-bounded so it terminates under a frozen test clock), and the `137` branch now captures the pane tail into stderr for diagnosis [source: claude_runner.py; source: tests/test_claude_runner.py].

`symphony-host.service` runs with `PrivateTmp=yes`, so per-run Claude tmux sockets live in the service's private `/tmp` (observe via `nsenter -t <MainPID> -m`); the #044 reaper glob operates within that namespace. A third, deeper bug surfaced once the pane capture worked: claude wrote the result via a Bash heredoc (`cat > result.txt << 'EOF'`) that broke on shell-special content (`command not found: bat`) and touched the done file anyway, leaving an empty result. The fix (C-0174) also hardens `_wrap_prompt`: claude is told to write the result with its **Write tool** (not a heredoc) and to create the done file **only after** verifying the result is non-empty. Live-verified 2026-06-13 ~06:54 UTC (restart on `2e8ff42`): Claude smoke issue 10 → Run 8 `succeeded`/`done`, completion comment carried the verbatim `**Symphony completed:**` block (backtick-heavy content literal, no header/Timeline/claim comment), `provider=''`/bare `claude-opus-4-8` — closing C-0154 on a successful scheduler Claude run.

## Verification

Ralph verification for #042 passed `uv run pytest -q` with 679 passed and 1 skipped, `uv run ruff check claude_runner.py tests/test_claude_runner.py`, `git diff --check`, and touched-file LSP diagnostics for Python files [source: .kanban/issues/042-claude-tmux-adapter.md]. Fresh Ralph review returned `RALPH_REVIEW: PASS` for the diff against base commit `2b6c976ef8f87e4c7d8ee3e09b46147a6ca7a5ed` [source: .kanban/issues/042-claude-tmux-adapter.md].
