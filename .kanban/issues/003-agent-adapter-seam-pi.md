---
id: 003
title: Agent Adapter seam (pi one-shot)
status: pending
blocked_by: []
parent: null
priority: 0
created: 2026-06-04
---

## What to build

Introduce an Agent Adapter interface that isolates an agent's dispatch shape
behind a common contract. Provide the **pi** implementation only: the existing
one-shot subprocess dispatch (`pi --print --no-session --provider … --model …`,
success from exit code, output captured for the verdict). The engine selects and
drives an adapter without knowing the agent's mechanics; the `SYMPHONY_RESULT` /
`SYMPHONY_SUMMARY` verdict parsing is reused unchanged.

This is the Agent Adapter seam from
`docs/adr/0001-claude-via-tmux-send-keys.md` and
`docs/adr/0002-generalize-symphony-over-adopting-a-platform.md`. Pure refactor —
pi behavior unchanged; the claude implementation is a later slice (#9).

## Acceptance criteria

- [ ] An `AgentAdapter` interface exists with a `PiAgentAdapter` implementation.
- [ ] pi dispatch goes through the adapter; the engine no longer shells out to pi directly.
- [ ] Verdict parsing (`SYMPHONY_RESULT`/`SYMPHONY_SUMMARY`, last-occurrence-wins, heuristic fallback) is reused via the adapter path.
- [ ] Existing pi dispatch behavior is unchanged (suite green).

## Verification

`uv run pytest`

## Blocked by

None — can start immediately.
