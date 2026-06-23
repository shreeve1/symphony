---
id: 103
title: Relax scheduler gate + resume, config, routing; wire the adapter
status: done
blocked_by: [102]
parent: 96
priority: 0
created: 2026-06-23
updated: 2026-06-23
actor: ralph
action_reviewed: 2026-06-23
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

## Verification

`.venv/bin/python -m pytest tests/test_scheduler.py tests/test_config.py tests/test_agent_runner.py -q && /usr/local/bin/ruff check scheduler/__init__.py config.py agent_runner.py main.py`

## Blocked by

- Blocked by #102

## Implementation Notes

- Relaxed the scheduler dispatch gate so remote Claude bindings can pass without the local Claude probe, while unsupported agents still fail loudly.
- Kept remote Claude resume cold by returning before local transcript eligibility checks.
- Allowed remote coding bindings to default to Claude without requiring RPC pi mode, while preserving remote coding and no-`claude_persist` guards.
- Routed remote Claude dispatch through the Claude adapter, wired `ClaudeAgentAdapter` to build `SshClaudeHost`, and passed remote fields from `main.build_binding_runtime`.
- Verification passed: `.venv/bin/python -m pytest tests/test_scheduler.py tests/test_config.py tests/test_agent_runner.py -q && /usr/local/bin/ruff check scheduler/__init__.py config.py agent_runner.py main.py`.
- Fresh review diffed `cc584c9211536c6555ce487f18f2fd9bff32a567..HEAD`, read every changed file, reran the exact verification command successfully, and returned `RALPH_REVIEW: PASS`.
