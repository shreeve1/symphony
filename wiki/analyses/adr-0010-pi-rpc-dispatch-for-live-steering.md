---
title: ADR-0010 — Dispatch pi via RPC for live mid-run Steering; Claude stays park-and-reply
type: analysis
status: promoted
created: 2026-06-13
updated: 2026-06-13
sources:
  - wiki/raw/adr-0010-pi-rpc-dispatch-for-live-steering.md
  - docs/adr/0010-pi-rpc-dispatch-for-live-steering.md
  - CONTEXT.md
  - .kanban/issues/050-pi-resume-end-to-end.md
  - agent_runner.py
  - scheduler.py
confidence: high
tags: [adr, pi, rpc, steering, dispatch, agent-adapter, capability-interface, proposed, design-stage]
---

# ADR-0010 — Dispatch pi via RPC for live mid-run Steering

ADR-0010 (`proposed`, 2026-06-13) decides to dispatch **pi via its native RPC protocol** (`pi --mode rpc` — JSON commands on stdin, JSONL events on stdout) so the operator can **steer a Run live, mid-task**, not only between Runs. The trigger was the operator goal of CLI-fidelity inside an Issue (explore, ask, be asked, redirect); the [session-resume backlog](../concepts/session-resume-continuity.md) (047–055) delivers the *async turn-taking* form of that (park → reply → resume + tail) but **deferred live mid-run steering** as a race-prone tmux-send-keys problem (`C-0176`) [source: wiki/concepts/session-resume-continuity.md].

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

ADR-0010 stays `proposed` for **live Steering** until #056/#057/#058 land; Slice A closes the prior "status stays proposed until #050 lands" gate for dispatch parity.

## Backlog re-sequencing

#047/#048/#049 stand (RPC-agnostic foundation). **#050 is done** (`PiRpcAgentAdapter`: dispatch parity + resume via `--session-id`; one-shot `PiAgentAdapter` retained as rollback, selected by `pi_mode`). #052 pi-side park parses `SYMPHONY_QUESTION` from the RPC final text (same marker contract as Claude). #053 tail stands (RPC persists the session jsonl when not `--no-session`). New issues: **#056** steer channel, **#057** steer UI flyout, **#058** RPC lifecycle/ops. Generalizes ADR-0001 and partially reverses the thin-engine "pi one-shot" posture.

## Claims

C-0178 (decision + parity spike + re-sequencing), plus C-0181..C-0183 for the landed #050 Slice A implementation. Supersedes the "deferred live tmux send-keys steering (Claude-only)" clause of C-0176. See [CLAIMS.md](../CLAIMS.md).
