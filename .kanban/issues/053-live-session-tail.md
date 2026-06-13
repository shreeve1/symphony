---
id: 053
title: Live Session Tail — stream the running agent's session file to the flyout
status: pending
blocked_by: [050, 051]
parent: null
priority: 0
created: 2026-06-13
updated: 2026-06-13
---

## What to build

Give the operator an in-flight, read-only view of a running Run by tailing the agent's session `.jsonl` (which the agent appends live during the run) and streaming it to the Podium issue flyout. This recovers in-flight visibility WITHOUT changing the separate-process scheduler architecture (ADR-0006): the per-Run disk log is only written once at process exit, but the session file is a live stream.

> **ADR-0010 note:** this approach is transport-agnostic and **stands as designed** — pi RPC (#050) persists the session `.jsonl` via `--session-id` (not `--no-session`), so the jsonl-tail source exists for both agents. No RPC-event plumbing required for tail. (An optional richer/lower-latency tail off the RPC event stream itself is possible later but is out of scope here.)

- Backend: for a running issue, resolve the derived session file path (#048 `session_file_path`), tail newly appended JSONL events, and fan them out over the existing WebSocket hub (#017) as a new event type (e.g. `run.tail`). Read-only; same-host file read of `~/.claude/projects/...` and `~/.pi/agent/sessions/...`.
- Frontend: a flyout panel that subscribes to the tail events for the open issue and renders the streamed tool-calls/reasoning/edits as they arrive; clears/rebinds when switching issues; degrades gracefully when no run is active or the session file is absent.

## Acceptance criteria

- [ ] A backend endpoint/event resolves the running issue's session file and emits appended JSONL events over the WS hub as they are written.
- [ ] No change to the scheduler process model; tailing is performed by the web/API process reading the file.
- [ ] Frontend flyout panel renders incoming tail events live for the open issue and rebinds correctly on issue switch.
- [ ] Absent/locked/empty session file degrades to an empty, non-erroring panel.
- [ ] Tail is strictly read-only (no writes to the session file).

## Verification

`uv run pytest web/api/tests/ -q` for the tail endpoint/fanout, AND the frontend e2e: `cd web/frontend && npm run test:e2e -- session-tail.spec.ts` asserting streamed tail content appears in the flyout.

## Blocked by

- Blocked by #050, #051
