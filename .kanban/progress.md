# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

# Conventions & Decisions

- `models.yml` allows at most one `default: true` entry per agent. Missing per-agent defaults are valid at catalog load time but block dispatch when an issue for that agent lacks `preferred_model`.
- Until Claude dispatch wiring lands, `_apply_dispatch_gate` still blocks non-`pi` agents before model mismatch checks.

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
