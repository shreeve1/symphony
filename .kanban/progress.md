# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

# Conventions & Decisions

- `models.yml` allows at most one `default: true` entry per agent. Missing per-agent defaults are valid at catalog load time but block dispatch when an issue for that agent lacks `preferred_model`.
- Claude dispatch is wired. A startup Claude probe failure blocks only Claude issues at the dispatch gate; Pi dispatch remains unaffected.
- Claude startup runs one global orphan tmux socket reaper for `/tmp/symphony-claude-*.sock` before per-binding reconcile.

# Iteration Log

## #041 Agent-aware model catalog with per-agent defaults — 2026-06-13

**What changed:** Added per-agent model defaults, made `resolve_model` require an agent, set `claude-opus-4-8` as the Claude default, and updated dispatch/startup call sites.
**Files:** model_catalog.py, models.yml, main.py, scheduler.py, plane_adapter.py, tests/test_model_catalog.py, tests/test_dispatch_gate.py, web/api/tests/test_issue_create.py, .claude/skills/symphony-models/SKILL.md, .kanban/issues/041-agent-aware-model-catalog.md
**Decisions:** Zero defaults for an agent remain valid at load time; dispatch blocks only when that agent needs an implicit default.
**Conventions established:** Explicit preferred models remain agent-agnostic in `resolve_model`; scheduler mismatch gate owns agent/model compatibility errors.
**Notes for next iteration:** #043 can remove the non-`pi` engine block and rely on the mismatch gate and per-agent catalog defaults.

## #042 ClaudeAgentAdapter tmux send-keys engine — 2026-06-13

**What changed:** Added `claude_runner.py` with a Python-native tmux send-keys Claude adapter, file-based result/done completion, ready-pattern polling, allowlisted environment, worktree-aware cwd selection, and idempotent cleanup.
**Files:** claude_runner.py, tests/test_claude_runner.py, .kanban/issues/042-claude-tmux-adapter.md
**Decisions:** Kept routing out of scope; the adapter requires a pre-resolved Claude model and fails before tmux launch if `issue.resolved_model` is empty.
**Conventions established:** Claude adapter stdout is authoritative result-file content; pane capture is ANSI-stripped stderr diagnostics only. Tests should drive tmux behavior through fake `run_func`/clock/sleep/tempdir seams.
**Notes for next iteration:** #043 can wire `RoutingAgentAdapter` to choose `ClaudeAgentAdapter` for resolved Claude issues and keep `reasoning_effort` suffixes out of Claude model argv.

## #043 Wire claude dispatch end-to-end — 2026-06-13

**What changed:** Wired `ClaudeAgentAdapter` into runtime construction and `RoutingAgentAdapter`, allowed Claude through the dispatch gate, stored Claude Run rows with empty provider and bare model id, isolated Claude verdict/summary/gate parsing to stdout, and kept context compaction on the Pi adapter.
**Files:** agent_runner.py, main.py, scheduler.py, tests/test_agent_runner.py, tests/test_dispatch_compaction.py, tests/test_dispatch_gate.py, tests/test_trading_podium_dispatch.py, .kanban/issues/043-wire-claude-dispatch.md
**Decisions:** Claude post-run parsing treats pane stderr as diagnostics only because it can echo prompt vocabulary; Pi continues scanning stdout+stderr. Context compaction remains engine housekeeping through Pi defaults even for Claude issues.
**Conventions established:** Non-Pi Run rows keep resolved provider/model verbatim; Claude resolved models never receive reasoning-effort suffixes.
**Notes for next iteration:** #044 can add Claude startup probe and orphan socket reaping now that real Claude dispatch routing exists.

## #044 Claude startup probe + orphan socket reaper — 2026-06-13

**What changed:** Added fail-soft Claude startup probing, module-level probe failure state, Claude-only dispatch blocking on probe failure, and a startup orphan tmux socket reaper.
**Files:** claude_runner.py, scheduler.py, main.py, tests/conftest.py, tests/test_claude_runner.py, tests/test_dispatch_gate.py, tests/test_main.py, .kanban/issues/044-claude-startup-probe-and-socket-reaper.md
**Decisions:** Missing or broken Claude support no longer fails Symphony boot; it blocks only Claude dispatch until the install is fixed and the service restarts.
**Conventions established:** Startup cleanup of Claude tmux sockets runs exactly once globally before per-binding reconcile; probe checks use `claude --version` only and never launch a live Claude session.
**Notes for next iteration:** #045 is frontend-only and should keep Playwright manual for UI flows unless explicitly requested.
