---
title: ADR-0019 — The orchestrator owns the agent's I/O (tracker port + remote run visibility)
type: analysis
status: promoted
created: 2026-06-21
updated: 2026-06-21
sources:
  - docs/adr/0019-orchestrator-owns-agent-io-tracker-port-and-remote-tail.md
  - proc_runtime.py
  - agent_runner.py
  - web/api/main.py
  - tests/test_agent_runner.py
  - web/api/tests/test_session_tail.py
  - wiki/raw/sessions/2026-06-21-remote-tail-and-tracker-port.md
confidence: high
tags: [adr, tracker-adapter, tracker-port, plane, podium, halo, agent-provisioning, remote-binding, ssh, session-tail, pi-rpc, spool, observability, extension-point, registry]
---

# ADR-0019 — The orchestrator owns the agent's I/O

Two threads from a Run #212 triage + grill-me session, joined by one principle: **the orchestrator (the scheduler process on aidev) is the single funnel point for both the tracker conversation and the agent's output stream; tracker-specific and deployment-specific detail belongs behind the adapter, not in the core engine.** Tracker-port half **proposed** (design locked, not built); remote-tail half **landed in the working tree 2026-06-21** (tested, not yet committed/deployed). [source: docs/adr/0019-orchestrator-owns-agent-io-tracker-port-and-remote-tail.md]

## Origin: Run #212 looked stuck but was healthy

Operator flagged Run #212 (binding `n8n`) as "not running correctly." It was a healthy remote run: issue #89, pi/`openai-codex` `gpt-5.5:high`, `running` 18:03:21Z → `succeeded`/verdict `review` 18:10:00Z, exit 0, `remote=true`. It only *looked* stuck because remote runs have no live tail. [source: wiki/raw/sessions/2026-06-21-remote-tail-and-tracker-port.md]

## Thread A — tracker port (proposed)

Plane is **dormant, not dead** — it is the second reference implementation of a pluggable tracker, with a third (Halo, a SaaS ITSM) on the roadmap. Today the Plane *name* leaks above the seam into tracker-agnostic engine code (`config.plane_api_url` drives the generic SSH reverse tunnel, `_uses_plane_tracker()` branches, `PlaneRateLimitError` in the scheduler, hardcoded `main.py` if/else selection).

Decision: the `TrackerAdapter` port has **two halves, both owned by each adapter** —
1. **Engine-side I/O** the scheduler calls (`list_candidates`, `transition_state`, `add_comment`, final verdict);
2. **Agent provisioning** the adapter *declares* — the CLI helper to ship (`plane_cli.py` → future `halo`), creds/env to inject, API endpoint to reach. Podium declares "nothing."

Every current leak is agent-provisioning logic that moves behind `adapter.agent_provisioning()`; the core then loops over `adapter.*` with no tracker name. A grill-me correction: **agent-during-run is the canonical model** (real ticketing surfaces — Plane, Halo, Jira — want the agent reading/writing tickets live), and Podium's scheduler-writes-after-exit is the local-only exception — the reverse of the agent's initial framing. Consequences: the reverse tunnel becomes a dispatch-layer inference (loopback-on-orchestrator + remote ⇒ tunnel; SaaS ⇒ direct outbound, no tunnel — which is why Run #212's `-R 8000` tunnel pointing at nothing was harmless); each binding gets an opaque `tracker_config:` block in `bindings.yml` (secrets stay in `symphony-host.env` by reference); selection becomes a registry, entry-point discovery deferred until a third-party author exists. Amends ADR-0005's "keep the seam" and ADR-0012's remote-callback. Not yet implemented — pairs with building the Halo adapter. [source: docs/adr/0019-orchestrator-owns-agent-io-tracker-port-and-remote-tail.md]

## Thread B — remote run visibility (landed in working tree)

Don't read the remote transcript over SSH (ADR-0012's `ssh tail -f` sketch needs a second connection per run). The scheduler **already receives** the remote agent's output as a live JSONL stream over the existing SSH pipe — both local and remote pi RPC funnel through `_drain_rpc_events`. So spool that stream to a local file the web tailer can read:

- `_drain_rpc_events` takes optional `spool_path` and mirrors each assistant delta to it; `run_remote_agent` passes `proc_runtime.tail_spool_path(run_id)` = `<runtime>/tail/<run_id>.log` and deletes it on run end. For remote bindings the file lands on aidev, written from the SSH stream — no remote-FS reach. [source: agent_runner.py] [source: proc_runtime.py]
- The web `_SessionTailer` reads the spool for remote bindings (via `_is_remote_binding`, with `r.id AS run_id` added to the poll query) and the native session file for local bindings (unchanged), reusing the existing incremental reader + WebSocket fanout. The lenient frontend (`SessionTailPanel.formatSessionTailLine` falls back to raw text) needs no change. [source: web/api/main.py]
- Scoped to remote (always pi RPC per ADR-0012); local pi's richer native-file tail and Claude's tmux tail are untouched.

Rejected alternative: republish RPC events straight to the WebSocket hub — the scheduler and web hub are **separate processes** (ADR-0006), so a cross-process channel is required anyway; the filesystem spool is that channel and matches the existing file-based tail pattern.

Verified: `tests/test_agent_runner.py::test_drain_rpc_events_spools_assistant_deltas` and `web/api/tests/test_session_tail.py::test_tailer_reads_spool_for_remote_binding`; `uv run pytest tests/test_agent_runner.py tests/test_remote_agent.py web/api/tests/test_session_tail.py` → 59 passed / 1 skipped; `ruff` clean. [source: tests/test_agent_runner.py] [source: web/api/tests/test_session_tail.py]

## Known ceiling

The spool records assistant deltas, not the native session file's full tool-call detail — an operator watching a remote run sees the agent's prose, not every tool invocation. Acceptable for liveness. The "no active session" placeholder now shrinks to the pre-first-token window instead of spanning the whole remote run.

## Follow-ups

- Remote-tail feature **committed (`0030694`) + spool size-cap (`5839869`, `TAIL_SPOOL_MAX_BYTES`=1 MiB, tmpfs safety) + deployed 2026-06-21** by restarting `symphony-host` (writer, `code_sha=5839869`, 5 bindings, clean) **and** `podium-api` (reader). `/run/symphony` shared channel verified (both run as `james`). **Not yet live-verified on a real remote run** — self-verifies on the next n8n/ai-web-chat dispatch.
- Build the tracker port + Halo adapter (Thread A).
