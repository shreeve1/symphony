---
id: 076
title: Add claude_persist per-binding config flag
status: pending
blocked_by: []
parent: null
priority: 0
created: 2026-06-17
---

## What to build

Add a per-binding `claude_persist: bool` flag (default `false`) that opts a binding into warm issue-scoped Claude sessions + live steering (ADR-0013). This slice is config-only: the flag parses, validates, defaults false, is rejected on remote bindings, and is reachable by the Claude adapter. No behaviour change yet — every existing path runs identically with the default.

Source: `plans/warm-claude-session-and-send-keys-steer.md` tasks 1.1–1.4.

## Acceptance criteria

- [ ] `ProjectBinding` (`config.py:80`) has `claude_persist: bool = False`.
- [ ] The binding parser (`config.py:~414`, near `pi_mode`) reads `claude_persist`, coerces a YAML bool, defaults `False`, and raises `ConfigError` naming `<prefix>.claude_persist` on a non-bool value.
- [ ] A remote binding with `claude_persist: true` raises `ConfigError` (Claude does not run remotely; ADR-0012). A remote binding with the flag absent/false parses fine.
- [ ] `ClaudeAgentAdapter` receives the flag (pass `persist=binding.claude_persist` at `main.py:174`, mirroring `RemoteAgentAdapter(config=, binding=)` at `main.py:162`); adapter stores it without using it yet.
- [ ] Existing `bindings.yml` (no `claude_persist` key) loads unchanged.

## Verification

`uv run pytest tests/test_config.py` and `uv run python -m py_compile config.py main.py agent_runner.py`

## Blocked by

None — can start immediately.
