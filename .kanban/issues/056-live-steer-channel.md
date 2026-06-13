---
id: 056
title: Live mid-run Steering channel (pi RPC) — Slice C
status: pending
blocked_by: [050]
parent: null
priority: 0
created: 2026-06-13
updated: 2026-06-13
---

## What to build

The core new capability of ADR-0010: let the operator inject a redirect **into a running pi Run** mid-task, via pi's RPC `steer` command, over a web→scheduler payload channel. This un-defers the live-steer item recorded as deferred in `wiki/concepts/session-resume-continuity.md` / `C-0176`. **pi-only** — Claude has no headless protocol for this account and keeps park-and-reply (#052).

The scheduler (holds the live `pi --mode rpc` process stdin) is a separate process from the web/API (ADR-0006), so the channel extends the #054 wake-sentinel pattern from a bare signal to a payload queue:

- **Web side:** a `POST /api/issues/{id}/steer` (and/or run-scoped) endpoint writes the operator's steer text as a record to a per-run queue — a file under the runtime dir (e.g. `/run/symphony/steer/<run_id>.jsonl`) or a DB-backed queue (shape decided in this issue; file-queue preferred for restart-tolerance and zero new daemon).
- **Scheduler/adapter side:** the `PiRpcAgentAdapter` event-pump loop (#050) polls the run's steer queue between event reads and forwards new records as `{"type":"steer","message":...}` on the RPC stdin. Steering is race-free by protocol: pi delivers it after the current tool calls, before the next LLM call.
- **Abort:** the same channel carries an abort/cancel record → `{"type":"abort"}`.
- **Addressing:** a run→queue registry so the web knows the queue path/key for the open issue's active run (run_id exists once the Run row is created). No steer accepted when no live RPC run is active for the issue (return a clear 409/empty state).

Steering messages must be persisted/observable enough to show in the UI (#057) and to survive a scheduler poll gap; the queue is drained, not replayed, once forwarded.

## Acceptance criteria

- [ ] A steer POST for an issue with a live RPC run writes a record the adapter forwards as an RPC `steer` command; the agent visibly acts on it after the current tool call.
- [ ] Steering an issue with no active RPC run is rejected cleanly (no crash, clear response).
- [ ] An abort record forwarded as RPC `abort` stops the run and maps to the existing timeout/abort `AgentResult` path.
- [ ] The channel is restart-tolerant (stale queue on boot does not wedge or mis-deliver) and decoupled (web never touches the subprocess directly).
- [ ] Claude runs reject/ignore steer with a clear "park-and-reply only" response (no tmux send-keys steering).
- [ ] Tests cover queue write→poll→forward with a faked RPC stdio and a faked clock/poll.

## Verification

`uv run pytest tests/test_scheduler*.py tests/test_agent_runner*.py web/api/tests/ -q`

## Blocked by

- Blocked by #050
