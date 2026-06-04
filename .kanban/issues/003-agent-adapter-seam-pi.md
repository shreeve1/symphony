---
id: 003
title: Agent Adapter seam (pi one-shot)
status: done
blocked_by: []
updated: 2026-06-04
actor: ralph
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

- [x] An `AgentAdapter` interface exists with a `PiAgentAdapter` implementation.
- [x] pi dispatch goes through the adapter; the engine no longer shells out to pi directly.
- [x] Verdict parsing (`SYMPHONY_RESULT`/`SYMPHONY_SUMMARY`, last-occurrence-wins, heuristic fallback) is reused via the adapter path.
- [x] Existing pi dispatch behavior is unchanged (suite green).

## Verification

`uv run pytest`

## Blocked by

None — can start immediately.

## Implementation Notes

Added an `AgentAdapter` protocol and `PiAgentAdapter` wrapper for the existing one-shot pi subprocess runner. Wired `main.py` to pass the pi adapter into the scheduler, while preserving the existing `AgentResult` path so verdict parsing remains unchanged. Verified with `uv run pytest`, critical LSP diagnostics for touched files, and mandatory fresh review (`RALPH_REVIEW: PASS`).
