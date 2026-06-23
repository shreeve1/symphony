---
id: 103
title: Relax scheduler gate + resume, config, routing; wire the adapter
status: done
blocked_by: [102]
parent: 96
priority: 0
created: 2026-06-23
updated: 2026-06-23
actor: pi
---

## What to build

Open the dispatch path so a remote coding binding with `default_agent: claude` reaches
the now-remote-aware Claude runner. Source of truth:
`plans/feature-remote-claude-dispatch.md` (Group 5).

- `scheduler/__init__.py` `_apply_dispatch_gate` (l.540-572): allow a remote binding whose
  resolved agent is `claude` (relax the remote-only-pi block); skip the local-claude-probe
  block for remote+claude (the remote host owns its claude/tmux).
- `scheduler/__init__.py` `_prepare_resume_candidate` (l.445): skip Session Resume for
  `binding.is_remote and agent == "claude"` BEFORE it calls `evaluate_resume_eligibility`
  (l.493). Otherwise the eligibility check reads the Claude transcript at the local
  `Path.home()` root (`session_continuity.py:48`) and a local transcript collision can
  render the remote run with `resumed=True`, contradicting the runner's fresh
  `--session-id`. Remote+claude must re-dispatch as a cold refeed.
- `config.py` (l.539-559): allow `default_agent in {pi, claude}` for remote; require
  `pi_mode == "rpc"` only when `default_agent == "pi"`; keep `claude_persist` forbidden
  and `type == "coding"` required for remote.
- `agent_runner.py` `RoutingAgentAdapter.__call__` (l.1122-1132): add a remote+claude
  branch that dispatches via the remote-aware claude adapter instead of raising.
- `ClaudeAgentAdapter` gains optional `remote` + `remote_repo_path`; when set it builds an
  `SshClaudeHost` and passes it + the remote start-dir into `run_claude_agent`.
- `main.py` `_build_binding_runtime` (l.198-205): build `ClaudeAgentAdapter` with the
  remote fields when the binding is remote.

## Acceptance criteria

- [x] Remote+claude passes `_apply_dispatch_gate`; remote+claude with a local
      claude-probe failure still passes (probe skipped for remote); prior remote-only-pi
      assertions updated.
- [x] `_prepare_resume_candidate` returns a cold (`resumed=False`) candidate for a
      remote+claude binding even when a same-named local Claude transcript exists.
- [x] Remote coding binding with `default_agent: claude` parses; remote+claude+
      `claude_persist` raises; remote+claude with `type != coding` raises.
- [x] `RoutingAgentAdapter` routes remote+claude → claude adapter; remote+pi → remote-pi
      adapter.
- [x] `main.py` `_build_binding_runtime` builds a `ClaudeAgentAdapter` with the remote
      fields for a remote+claude binding (asserted in `tests/test_main.py`).

## Verification

`.venv/bin/python -m pytest tests/test_scheduler.py tests/test_config.py tests/test_agent_runner.py tests/test_main.py -q && /usr/local/bin/ruff check scheduler/__init__.py config.py agent_runner.py main.py`

## Blocked by

- Blocked by #102

## Implementation Notes

- Relaxed the remote scheduler dispatch gate for Claude and skipped the local Claude startup probe for remote+Claude.
- Kept remote+Claude on cold refeed by bypassing Session Resume eligibility before local transcript checks.
- Relaxed remote config invariants to allow `default_agent: claude`, while keeping remote `claude_persist` and non-coding rejections; remote Pi still requires `pi_mode: rpc`.
- Routed remote+Claude through the Claude adapter; wired `ClaudeAgentAdapter` to construct `SshClaudeHost` and pass `remote_start_dir`.
- Verification passed: `.venv/bin/python -m pytest tests/test_scheduler.py tests/test_config.py tests/test_agent_runner.py tests/test_main.py -q && /usr/local/bin/ruff check scheduler/__init__.py config.py agent_runner.py main.py`.
- Extra coverage passed: `tests/test_remote_agent.py tests/test_claude_runner.py` and ruff on touched tests/files.
- Wave audit retried with pi after an initial timeout; retry passed with 0 critical / 0 warning / 1 note, then the note was addressed with explicit remote+Claude config guard tests. Logged in `plans/.feature-remote-claude-dispatch.state.yml`.
