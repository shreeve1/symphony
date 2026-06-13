---
id: 041
title: Agent-aware model catalog with per-agent defaults
status: in-progress
blocked_by: []
parent: null
priority: 1
created: 2026-06-13
updated: 2026-06-13
actor: ralph
---

## What to build

Make model resolution agent-aware so each agent in `KNOWN_AGENTS` can carry its own catalog default, per the ADR-0001 amendment (`docs/adr/0001-claude-via-tmux-send-keys.md`). This slice is behavior-neutral for live dispatch: claude issues remain blocked by the final "engine is not wired" check in `_apply_dispatch_gate` until #043 removes it.

Changes:

1. `model_catalog.py` — `validate_models`: replace the global "exactly one `default: true`" rule with **at most one `default: true` per agent**. Two defaults for the same agent is a validation error naming the agent and both model ids. Zero defaults for an agent is valid at load time.
2. `model_catalog.py` — `resolve_model(preferred_model, models, agent)`: gains a required `agent` parameter. Explicit `preferred_model` behaves exactly as today (match by id or raise `ModelResolutionError`; the agent/entry mismatch check stays the gate's job). When no `preferred_model`, select the `default: true` entry whose `agent` matches; if that agent has no default, raise `ModelResolutionError` with a message naming the agent ("models.yml has no default: true entry for agent `claude`").
3. `models.yml` — add `default: true` to `claude-opus-4-8`. `gpt-5.5` keeps its default.
4. `main.py` (the `resolve_model(None, load_models())` startup-probe call, currently line 91) — pass `agent="pi"`.
5. `scheduler.py` `_apply_dispatch_gate` — pass the resolved agent into `resolve_model`; change the hardcoded `entry["agent"] != "pi"` check to `entry["agent"] != agent` with a mismatch message of the shape: "Dispatch blocked: model `<id>` requires agent `<entry agent>` but the issue resolves to agent `<agent>`; pick a matching model or change preferred_agent." Keep the earlier `agent != "pi"` → "engine is not wired" block in place and FIRST, so claude dispatch behavior is unchanged by this slice.
6. Update any other `resolve_model` call sites (grep for them, including `web/api/`) to pass an agent.

## Acceptance criteria

- [ ] `validate_models` accepts one pi default + one claude default simultaneously; rejects two pi defaults or two claude defaults with an error naming the agent.
- [ ] `resolve_model(None, models, agent="claude")` returns `claude-opus-4-8`; `resolve_model(None, models, agent="pi")` returns `gpt-5.5`; missing per-agent default raises `ModelResolutionError` naming the agent.
- [ ] Explicit `preferred_model` resolution is unchanged (match or loud `ModelResolutionError`), regardless of agent.
- [ ] `models.yml` carries `default: true` on `claude-opus-4-8` and still loads via `load_models()`.
- [ ] `_apply_dispatch_gate` blocks an agent/model mismatch (pi agent + claude model) with the new message; pi agent + pi model still dispatches; claude agent still blocks with "engine is not wired".
- [ ] Startup pi probe path works (the `main.py` call site passes `agent="pi"` and existing startup tests stay green).
- [ ] `uv run pytest` green.

## Verification

`uv run pytest`

## Blocked by

None - can start immediately
