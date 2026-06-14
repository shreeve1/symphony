---
title: ADR-0010 — Dispatch pi via RPC for live mid-run Steering; Claude stays park-and-reply
type: analysis
status: promoted
created: 2026-06-13
updated: 2026-06-14
sources:
  - wiki/raw/adr-0010-pi-rpc-dispatch-for-live-steering.md
  - docs/adr/0010-pi-rpc-dispatch-for-live-steering.md
  - CONTEXT.md
  - .kanban/issues/050-pi-resume-end-to-end.md
  - .kanban/issues/056-live-steer-channel.md
  - .kanban/issues/057-steer-ui-flyout.md
  - .kanban/issues/058-rpc-lifecycle-ops.md
  - tests/test_agent_runner.py
  - tests/test_scheduler.py
  - agent_runner.py
  - scheduler.py
  - web/api/main.py
  - web/api/steer_queue.py
  - web/frontend/components/IssueFlyout.tsx
  - web/frontend/components/QueryProvider.tsx
  - web/frontend/tests/steer-flyout.spec.ts
confidence: high
tags: [adr, pi, rpc, steering, dispatch, agent-adapter, capability-interface, accepted, implemented]
---

# ADR-0010 — Dispatch pi via RPC for live mid-run Steering

ADR-0010 (`accepted`, 2026-06-13) decides to dispatch **pi via its native RPC protocol** (`pi --mode rpc` — JSON commands on stdin, JSONL events on stdout) so the operator can **steer a Run live, mid-task**, not only between Runs. The trigger was the operator goal of CLI-fidelity inside an Issue (explore, ask, be asked, redirect); the [session-resume backlog](../concepts/session-resume-continuity.md) (047–055) delivers the *async turn-taking* form of that (park → reply → resume + tail) but **deferred live mid-run steering** as a race-prone tmux-send-keys problem (`C-0176`) [source: wiki/concepts/session-resume-continuity.md].

## The decision and why one mechanism is unreachable

The handoff's leading hypothesis was "switch pi to tmux to standardize on Claude's dispatch shape." Rejected. Two verified facts invert it [source: wiki/raw/adr-0010-pi-rpc-dispatch-for-live-steering.md]:

- **pi has a clean headless protocol.** `pi --mode rpc`'s `steer` command is race-free by construction — delivered *after the current tool calls finish, before the next LLM call* — the exact mid-run interjection point tmux send-keys cannot hit safely. It also gives deterministic completion (`agent_end`), `abort`, a full event stream (= live tail), and native sessions.
- **Claude has none for this account.** `claude --output-format stream-json` is gated behind `--print`, and `claude -p` headless was removed for this subscription (`C-0016`, ADR-0001/0002). The interactive TUI driven by tmux send-keys is the only authenticated surface.

So a single dispatch mechanism is impossible: "both on tmux" drags the proven pi path onto the fragile mechanism (`C-0174` race class) and re-thickens the thin engine; "both on streaming" is blocked by the account. The decision instead **standardizes the Agent Adapter *capability* interface, not the transport** — the engine asks an adapter for completion, tail, and steer, and each agent satisfies them in its own transport. **pi pivots to RPC; Claude stays tmux park-and-reply; live Steering is pi-only.**

## New architecture: the inward steer channel

The one genuinely new piece is a control channel from the web/API process to the live agent process. ADR-0006 made the scheduler a separate process that surfaces engine state by polling *outward* only; live steer is the inverse (operator input flowing *inward* to a running subprocess's stdin). ADR-0010 extends — does not overturn — ADR-0006 by reusing the seam #054 establishes: where #054 writes a wake *sentinel* the scheduler polls, live steer writes **steer payloads** to a per-run queue the pi adapter's event-pump loop polls and forwards as RPC `steer` commands. The synchronous adapter contract (`__call__ -> AgentResult`) becomes an internal event-pump loop but still returns one `AgentResult` whose `stdout` is the final assistant text, so the downstream verdict scrape (`scheduler.py:233`) is unchanged.

## Parity spike (PASSED 2026-06-13)

Gate for the ADR. In a throwaway dir with `--no-session` (no infra touched): `pi --mode rpc --skill <dir>` loaded the skill (`skill:symphony-models` appeared in `get_commands`), resolved provider/model (`openai-codex`/`gpt-5.4-mini` via `get_state`), loaded CLAUDE.md context (correctly answered the project's required prose style), streamed `message_update` text deltas (live tail), and completed deterministically on `agent_end`. RPC has full `--print` dispatch parity plus the interactive protocol.

## Slice A landed (#050)

#050 landed the in-app pi RPC adapter and resume wiring. `PiRpcAgentAdapter` now builds `pi --mode rpc ... --session-id <derived>`, sends a JSON prompt command, pumps stdout JSONL until `agent_end`, sends RPC `abort` on timeout, and returns the final assistant text in `AgentResult.stdout`, preserving downstream verdict/summary parsing. `pi_mode: rpc` is the per-binding opt-in; one-shot `PiAgentAdapter` remains the default rollback path. Scheduler resume wiring evaluates #048 eligibility for pi RPC bindings, renders #049 delta prompts on resume, records `resumed`/`agent_session_sha`, skips context compaction on resume, and falls back to fresh full re-feed on predicate or runtime failure. [source: agent_runner.py] [source: scheduler.py] [source: .kanban/issues/050-pi-resume-end-to-end.md]

Slice A (#050) closed dispatch parity; the full-path soak in C-0190 moved ADR-0010 to `accepted`. Live Steering is implemented through #058: #056 landed the channel, #057 landed the operator UI, and #058 closed the remaining RPC lifecycle/ops hardening.

## Live Steering channel and UI landed (#056/#057)

#056 landed the core inward control channel. `POST /api/issues/{id}/steer` accepts `steer` and `abort` requests only for a live running pi RPC Run, rejects Claude with a park-and-reply message, writes a transient per-run queue record under `SYMPHONY_RUNTIME_DIR/steer/<run_id>.jsonl`, appends durable `### Operator Steer` / `### Operator Abort` blocks to `comments_md` without flipping state, and publishes the updated Issue. `run_pi_rpc_agent` polls the queue inside the RPC event pump and forwards queued records as RPC `steer` / `abort` commands. [source: web/api/main.py] [source: web/api/steer_queue.py] [source: agent_runner.py] [source: .kanban/issues/056-live-steer-channel.md]

#057 landed the operator surface in the Podium flyout Session tab. The UI exposes a steer textarea and abort button only when the open Issue has an active running pi RPC Run, shows disabled affordances for Claude / idle / non-RPC cases, calls the #056 endpoint via typed `postSteer` / `postAbort` clients, adds local queued/delivered tail echoes through the existing `QueryProvider` tail buffer, and relies on the API's `comments_md` append for the durable thread. `/api/bindings` now exposes each binding's `pi_mode` so the frontend can gate the affordance without parsing `bindings.yml`. [source: web/frontend/components/IssueFlyout.tsx] [source: web/frontend/components/QueryProvider.tsx] [source: web/frontend/lib/api.ts] [source: web/api/main.py] [source: .kanban/issues/057-steer-ui-flyout.md]

## RPC lifecycle hardening landed (#058)

#058 closed the lifecycle/ops gap left after the initial real-binding RPC flip. `run_pi_rpc_agent` already enforced wall-clock timeout with RPC `abort` and pidfile cleanup; this slice added transient steer-queue cleanup on every adapter exit path, startup cleanup for stale steer queues inside `reap_orphan_rpc_processes`, and explicit tests for both cleanup paths and semaphore cap accounting. The startup reaper now logs both orphan process count and stale queue count in `rpc_orphan_reap_done`, and live RPC runs continue to occupy the existing `_dispatch_one` semaphore slot rather than using separate RPC-specific accounting. [source: agent_runner.py] [source: web/api/steer_queue.py] [source: tests/test_agent_runner.py] [source: tests/test_scheduler.py] [source: .kanban/issues/058-rpc-lifecycle-ops.md]

## Backlog re-sequencing

#047/#048/#049 stand (RPC-agnostic foundation). **#050 is done** (`PiRpcAgentAdapter`: dispatch parity + resume via `--session-id`; one-shot `PiAgentAdapter` retained as rollback, selected by `pi_mode`). #052 pi-side park parses `SYMPHONY_QUESTION` from the RPC final text (same marker contract as Claude). #053 tail stands (RPC persists the session jsonl when not `--no-session`). **#056, #057, and #058 are done** (live steer channel, flyout UI, and RPC lifecycle hardening). Generalizes ADR-0001 and partially reverses the thin-engine "pi one-shot" posture.

## Claims

C-0178 (decision + parity spike + re-sequencing), C-0181..C-0183 for the landed #050 Slice A implementation, C-0190 for acceptance/full-path soak, C-0193 for landed #056/#057 live steering channel + UI, and C-0194 for #058 lifecycle hardening. Supersedes the "deferred live tmux send-keys steering (Claude-only)" clause of C-0176. See [CLAIMS.md](../CLAIMS.md).
