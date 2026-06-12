---
id: 040
title: Wire a real Claude engine adapter (claude -p) behind the dispatch gate
status: pending
blocked_by: []
parent: null
priority: 1
created: 2026-06-12
updated: 2026-06-12
actor: ralph
---

## What to build

The dispatch gate (scheduler `_apply_dispatch_gate`) currently blocks any issue whose agent resolves to `claude` with "claude engine is not wired (pi only)". `RoutingAgentAdapter` (agent_runner.py) routes everything to `PiAgentAdapter`. Wire a real `ClaudeAgentAdapter` so `preferred_agent: claude` issues dispatch through Claude Code headless mode instead of blocking.

Contract:

- Invoke `claude -p "<rendered prompt>"` (headless print mode) with the binding repo (or worktree) as cwd, mirroring `run_agent`'s env scrubbing, timeout (`config.run_timeout_ms`), and process-group termination semantics.
- Model: resolve from `models.yml` claude entries via `model_catalog.resolve_model` (the gate already resolves the entry; extend it to allow `agent: claude` entries when the claude adapter is available, and pass the model id via `--model`).
- `reasoning_effort` mapping for claude (e.g. thinking budget flag or omit) — decide and document; do not silently drop the field.
- Skill loading: claude discovers `~/.claude/skills` natively, so no `--skill` flag is needed; keep the prompt's prepended skill directive as-is.
- Parse the SYMPHONY_RESULT marker from stdout exactly like the pi path so verdict extraction (`done`/`review`/`blocked`) is engine-agnostic.
- Record run rows honestly: `agent="claude"`, provider (e.g. `anthropic`), resolved model, cost/token metrics if extractable from claude JSON output (`--output-format json`), else NULL.
- `RoutingAgentAdapter` routes on the gate's resolved agent; pi path behavior must be byte-for-byte unchanged.
- Update `_apply_dispatch_gate` tests: claude no longer blocks when the adapter is wired; claude model entries resolve for claude agent.
- Startup probe: a `verify_claude_support` analogous to `verify_pi_support` (binary present, `-p` supported) gated on any binding/issue actually using claude — startup must not fail for pi-only deployments when claude is absent.

## Acceptance criteria

- [ ] Issue with `preferred_agent: claude` + a `models.yml` claude model dispatches via `claude -p` and lands a run row with agent=claude and the real model id.
- [ ] Pi dispatch path unchanged (existing tests green, no new argv entries on pi runs).
- [ ] Gate tests updated: unknown claude model still blocks; claude entry + claude agent passes.
- [ ] Timeout/termination parity with pi path (TimeoutExpired -> SIGTERM group -> SIGKILL).
- [ ] `uv run pytest` green.
