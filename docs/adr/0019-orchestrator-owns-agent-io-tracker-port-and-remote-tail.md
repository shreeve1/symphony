# The orchestrator owns the agent's I/O: a tracker port and remote run visibility

Status: tracker-port half **proposed**; remote-tail half **accepted, landed 2026-06-21**

## Context

Two threads converged on one principle. Both started from the observation that
Symphony's core engine reaches *around* its own abstraction seams and bakes in
assumptions about a single deployment.

**Thread A — the tracker seam leaks.** All live bindings use `tracker: podium`,
but Plane is not dead code — it is the second reference implementation of a
pluggable tracker, and a third (Halo, a SaaS ITSM) is on the roadmap. Yet the
Plane *name* leaks above the seam into tracker-agnostic engine code:
`config.plane_api_url` drives the generic remote SSH reverse tunnel
(`agent_runner._remote_callback_port`), `_uses_plane_tracker()` branches decide
helper-shipping and callback env, `PlaneRateLimitError` is imported into the
scheduler for generic rate-limit handling, and adapter selection is a hardcoded
`if tracker == "podium"/else plane` in `main.py`. A new tracker can't be added
without editing core.

A grilling session corrected an initial instinct: Podium (local SQLite,
scheduler-writes-after-exit, agent gets no tracker access) is the *oddball*. Real
ticketing surfaces — Plane, Halo, Jira — want the agent to interact with the
tracker *during* the run: read linked tickets, post progress, update fields. So
the **agent-during-run model is canonical**, and Podium's scheduler-writes model
is the local-only exception — the reverse of the original framing.

**Thread B — remote runs are invisible.** Remote bindings dispatch the agent over
SSH (`pi --mode rpc`, ADR-0012). The agent's session transcript lives on the
*remote* host, so the web Live Session Tail — which reads a local session file —
silently finds nothing (`_read_new_lines` swallows the `OSError`) and shows "no
active session" for the whole run. Operators can't tell a healthy remote run from
a hung one (this is what prompted the Run #212 investigation). ADR-0012 deferred
this as "Session Tail over SSH (`ssh host tail -f`)" — a second SSH connection per
running issue.

## Decision

**Principle: the orchestrator (the scheduler process on aidev) owns the agent's
I/O.** It is the single funnel point for both the tracker conversation and the
agent's output stream; tracker-specific and deployment-specific detail belongs
behind the adapter, not in the core engine.

### Thread A — tracker port (proposed; design locked, not yet built)

The `TrackerAdapter` port has **two halves, both owned by each adapter**:

1. **Engine-side I/O** — what the scheduler calls: `list_candidates`,
   `transition_state`, `add_comment`, apply-final-verdict. Every tracker
   implements this.
2. **Agent provisioning** — what the adapter *declares the agent needs* to talk
   to the tracker live: the CLI helper to ship (today's `plane_cli.py` →
   future `halo` helper), the creds/env to inject, and the API endpoint to reach.
   Podium declares "nothing." Plane/Halo declare their helper + creds + endpoint.

Every current leak (`_uses_plane_tracker`, the `plane_api_url`-derived port,
`PLANE_*` env, conditional helper shipping) is agent-provisioning logic that
moves *into* the adapter behind `adapter.agent_provisioning()`. The core engine
then loops over `adapter.*` with no tracker name in it. Adding a tracker =
implement engine-I/O + declare provisioning.

Consequences:
- The SSH reverse tunnel stops being a Plane concept. The adapter says "the agent
  must reach `<api_url>`"; the dispatch layer sets up a reverse tunnel **iff**
  that URL is loopback-on-the-orchestrator and the binding is remote
  (self-hosted-on-aidev Plane → tunnel; SaaS Halo → direct outbound, no tunnel).
  This is why Run #212 (podium, no agent callback) succeeded despite its
  `-R 8000` tunnel pointing at nothing.
- Each binding gets an opaque `tracker_config:` block in `bindings.yml` passed
  verbatim to the adapter constructor; secrets stay in `symphony-host.env` and
  are referenced by name. The flat `plane_*` fields on the global config go away.
- Selection becomes a registry dict (`{"podium", "plane", "halo"}`) replacing the
  `main.py` if/else. Python entry-point discovery for *third-party* adapters is
  deferred until an external author exists; Halo is first-party and registers
  like a built-in.

This amends ADR-0005's "keep the `tracker:plane|podium` seam" and ADR-0012's
remote-callback wiring. Not yet implemented — it pairs with building the Halo
adapter.

### Thread B — remote run visibility (accepted, landed)

Don't read the remote transcript over SSH. The scheduler *already receives* the
remote agent's output as a live JSONL stream over the existing SSH pipe — both
local and remote pi RPC funnel through `_drain_rpc_events`. So **spool that
stream to a local file the web tailer can read.**

- `_drain_rpc_events` takes an optional `spool_path` and mirrors each assistant
  delta to it; `run_remote_agent` passes `proc_runtime.tail_spool_path(run_id)`
  (`<runtime>/tail/<run_id>.log`) and deletes it when the run ends. For remote
  bindings this file lands on aidev, written from the SSH stream — no remote-FS
  reach, no second connection.
- The web `_SessionTailer` reads the spool for remote bindings (via
  `_is_remote_binding`) and the native session file for local bindings
  (unchanged), reusing the existing incremental reader and WebSocket fanout.
- Scoped to remote (always pi RPC per ADR-0012), so local pi's richer native-file
  tail and Claude's tmux tail are untouched.

## Considered alternatives (Thread B)

- **`ssh host tail -f` the remote transcript** (ADR-0012's sketch) — rejected: a
  second SSH connection per running issue, and it must locate the remote pi
  session file. The scheduler already holds the stream; spooling it is strictly
  less plumbing.
- **Republish RPC events directly to the WebSocket hub** — rejected for now: the
  scheduler and web hub are separate processes (ADR-0006), so a cross-process
  channel is required anyway; the filesystem spool is that channel and matches
  the existing file-based tail pattern.

## Consequences

- Known ceiling: the spool records assistant deltas, not the native session
  file's full tool-call detail; an operator watching a remote run sees the
  agent's prose, not every tool invocation. Acceptable for liveness; revisit if
  remote debugging needs the richer view.
- The "no active session" placeholder window now shrinks to the pre-first-token
  period instead of spanning the whole remote run.
