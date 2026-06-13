---
id: 042
title: ClaudeAgentAdapter — tmux send-keys engine (fake-driven, unrouted)
status: review
blocked_by: []
parent: null
priority: 1
created: 2026-06-13
updated: 2026-06-13
actor: ralph
---

## What to build

A Python-native claude engine implementing the `AgentAdapter` protocol (`agent_runner.py`), per the ADR-0001 amendment (`docs/adr/0001-claude-via-tmux-send-keys.md`). Hard constraint: `claude -p` / print mode is NOT available — claude runs as an interactive TUI inside tmux. Port the mechanics of `~/.claude/skills/dev-review-claude/engine.sh` (readable reference; do not vendor or shell out to it). This slice builds and unit-tests the component only; routing/gate wiring is #043.

Create `claude_runner.py` (keeps `agent_runner.py` pi-focused) with `run_claude_agent(config, issue, rendered_prompt, ...)` and a frozen dataclass `ClaudeAgentAdapter` mirroring `PiAgentAdapter`. All subprocess/tmux/clock/sleep interactions go through injectable callables (same style as `run_agent`'s `popen_factory`/`clock`/`run_func` parameters) so tests drive the engine with fakes.

Contract:

- **Per-run artifacts** namespaced `symphony-claude-<issue.id>-<nonce>` (fresh random nonce per run; run id does not exist at the adapter seam): tmux socket `/tmp/symphony-claude-<issue.id>-<nonce>.sock`, session name, prompt file, result file, done file under a per-run temp dir. Never use the `drc-*` namespace.
- **Env allowlist**: PATH, HOME, USER, LANG, TMPDIR, XDG_RUNTIME_DIR, plus `SYMPHONY_ISSUE_ID`. No `TERM=dumb`, no `NO_COLOR`, no `plane` helper injection, no Plane env vars.
- **Launch**: `tmux -S <socket> new-session -d -s <session>` running `claude --permission-mode bypassPermissions --model <model>` in the run cwd (worktree path when `issue.worktree_active`, created exactly as `run_agent` does via `create_worktree`; else the binding repo checkout). Model value comes from `issue.resolved_model` verbatim (bare catalog id — #043's gate guarantees no `:effort` suffix for claude).
- **Ready poll**: poll `capture-pane` for the ready pattern (`bypass permissions on|shift\+tab to cycle`, case-insensitive) with a bounded ~30s window. On timeout: kill session, return synthetic failure (exit 1, `timed_out=False`), stderr = ANSI-stripped pane tail prefixed `claude_ready_timeout`.
- **Prompt delivery**: write the wrapped prompt to the prompt file, `tmux load-buffer` + `paste-buffer`, then send Enter. The wrapper preamble (adapter-level; rendered prompt passed through untouched) must state: unattended run, nobody will respond, never ask questions or end the turn awaiting input; write full output including a `SYMPHONY_RESULT: done|review|blocked` line (and optional `SYMPHONY_SUMMARY:`) to the literal result-file path via Bash, write the result file FIRST, then `touch` the literal done-file path; if genuinely blocked, write `SYMPHONY_RESULT: blocked` and still touch the done file; if the issue has a `preferred_skill`, invoke that skill by name.
- **Completion poll**: loop with injected sleep; completion requires done file exists AND result file non-empty (two-condition gate). Also check session liveness (`tmux has-session`) each cycle. Wall clock cap `config.run_timeout_ms`.
- **Six lifecycle mappings** (`AgentResult`): (1) ready-pattern timeout → exit 1 fast synthetic failure; (2) done + non-empty result → exit 0, stdout = result-file content, stderr = ANSI-stripped full pane capture; (3) session dead without done file → exit 1, stderr = pane tail; (4) done file but result missing or empty → exit 137 (mirror `pi_silent_exit`, loud message); (5) non-empty result without a `SYMPHONY_RESULT` marker is NOT a failure — return exit 0 and let the scheduler's existing markerless default (`review`) apply; (6) `run_timeout_ms` elapsed → kill session, `AgentResult(-1, ..., timed_out=True)`, stderr = pane tail.
- **Guard**: an empty `issue.resolved_model` is a fail-loud `AgentRunnerError` before any tmux call (only Podium-gated candidates carry resolved fields; never invoke `claude --model ""`, never fall back to `config.pi_model`).
- **Cleanup**: `finally`-guaranteed and idempotent — kill session, remove socket and the per-run temp dir. Structured log lines mirroring the pi path (`claude_dispatch issue_id=... model=... cwd=...`, `agent_exited ...`).
- Reuse `_strip_ansi` from `agent_runner.py` (import or move it somewhere shared).

## Acceptance criteria

- [ ] Fake-driven unit tests cover all six lifecycle mappings, asserting exit code, `timed_out`, stdout source (result file) and stderr source (pane) for each.
- [ ] Artifact paths in the issued tmux commands match `symphony-claude-<issue.id>-<nonce>` naming; nonce differs across two runs of the same issue.
- [ ] Preamble written to the prompt file contains the literal result-file and done-file paths, the never-ask instruction, and the skill directive when `preferred_skill` is set (absent when not).
- [ ] Env passed to the launch call contains only the allowlisted keys + `SYMPHONY_ISSUE_ID`; no TERM/NO_COLOR overrides.
- [ ] Worktree case: when `issue.worktree_active` is true the cwd is the created worktree path (fake `create_worktree`), else the binding repo path.
- [ ] Cleanup runs on every path including exceptions (assert kill+remove called after a fake raising mid-poll), and a second cleanup call does not raise.
- [ ] Empty `resolved_model` raises `AgentRunnerError` without launching tmux.
- [ ] No production code path invokes `engine.sh` or `claude -p`.
- [ ] `uv run pytest` green.

## Verification

`uv run pytest`

## Blocked by

None - can start immediately
