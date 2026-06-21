# Session Capture: Run #212 triage → remote session tail + tracker-port design (ADR-0019)

- Date: 2026-06-21
- Purpose: Operator reported Run #212 (binding `n8n`) "doesn't look like it's running correctly." Triage found a healthy remote run that merely *looked* stuck; a grill-me session then designed a pluggable tracker port (Halo roadmap) and built live visibility for remote runs.
- Scope: Run #212 diagnosis; the "orchestrator owns the agent's I/O" principle; ADR-0019 (tracker-port half proposed, remote-tail half landed in working tree); the dead `-R 8000` Plane tunnel finding.

## Durable Facts

- **Run #212 was healthy, not broken.** Issue #89 (binding `n8n`, agent pi/`openai-codex` `gpt-5.5:high`), `running` 18:03:21Z → `succeeded`/verdict `review` 18:10:00Z (~6m39s, `timed_out=false`, exit 0); issue → `in_review`. — Evidence: read-only `podium.db` `run`/`issue` rows; `journalctl -u symphony-host.service` `agent_exited issue_id=89 … remote=true`; `runs/212.log`.
- **Remote runs look stuck because there is no live tail for them (pre-fix).** The agent transcript lives on the remote host; the web `_SessionTailer` reads a *local* session file, `_read_new_lines` swallows the `OSError`, and the UI shows "no active session" for the whole run. Same local-FS check disables native resume for remote (ADR-0012 C-0252). — Evidence: `web/api/main.py` `_SessionTailer`, `session_continuity.session_file_path`.
- **The `-R 8000:127.0.0.1:8000` reverse tunnel is Plane-only legacy, dead for podium.** It is derived from `config.plane_api_url` (`agent_runner._remote_callback_port`, default 8000). Nothing listens on local 8000 (podium-api is `127.0.0.1:8090`); podium remote agents never call back (scheduler writes the local SQLite after exit), and the `plane` CLI helper that would use it is shipped only when `_uses_plane_tracker()` is true (never, all bindings `tracker: podium`). Run #212 succeeded despite the tunnel pointing at nothing. — Evidence: `agent_runner.py:437,608`, `ssh_support.ssh_base_args`, live `ps`/`ss`.
- **Plane is dormant, not dead — it is the 2nd reference tracker adapter.** `plane_adapter.py`/`plane_cli.py`/`HttpxPlaneTransport` + ~1,500 lines of tests are reachable only via `tracker: plane` (binding default is still `"plane"`, `config.py:506`); no live binding uses it. James wants to keep it and add a 3rd (Halo, SaaS ITSM) behind a genuine extension point.

## Decisions

- **Principle: the orchestrator owns the agent's I/O** (ADR-0019). Tracker-specific and deployment-specific detail belongs behind the adapter, not in the core engine. — Evidence: `docs/adr/0019-orchestrator-owns-agent-io-tracker-port-and-remote-tail.md`.
- **Tracker port (proposed, not built):** `TrackerAdapter` has two halves each adapter owns — engine-side I/O *and* agent-provisioning (helper to ship + creds/env + API endpoint). Core loops over `adapter.*` with no tracker name. **Agent-during-run is the canonical model** (Plane/Halo); Podium scheduler-writes-after-exit is the local-only exception (this *reversed* the agent's initial instinct). Reverse tunnel becomes a dispatch-layer inference (loopback+remote ⇒ tunnel; SaaS ⇒ direct). Opaque `tracker_config:` block in `bindings.yml`; registry replaces `main.py` if/else; entry-point discovery deferred. — Evidence: ADR-0019; grill-me session.
- **Remote tail (built this session, in working tree):** don't `ssh tail -f` the remote transcript — the scheduler already receives the pi RPC stream over the SSH pipe, so spool it to a local file the tailer reads. `_drain_rpc_events(spool_path=…)` mirrors assistant deltas to `proc_runtime.tail_spool_path(run_id)` (`<runtime>/tail/<run_id>.log`); `run_remote_agent` passes it and deletes on exit; `_SessionTailer` reads the spool for remote bindings, native file for local. Scoped to remote (always pi RPC). — Evidence: diff to `proc_runtime.py`, `agent_runner.py`, `web/api/main.py`; new tests.

## Evidence

- `docs/adr/0019-orchestrator-owns-agent-io-tracker-port-and-remote-tail.md` — the decision record (two halves).
- `proc_runtime.py` (`tail_spool_path`), `agent_runner.py` (`_drain_rpc_events` spool, `run_remote_agent` wiring + cleanup), `web/api/main.py` (`_SessionTailer` remote branch, `r.id AS run_id`) — the landed remote-tail feature.
- `tests/test_agent_runner.py::test_drain_rpc_events_spools_assistant_deltas`, `web/api/tests/test_session_tail.py::test_tailer_reads_spool_for_remote_binding` — verification (`uv run pytest` 59 passed/1 skipped; `ruff` clean).

## Exclusions

- No env files or live secrets read (`symphony-host.env` untouched). Telegram bot token visible in journal output was not captured.
- Tracker-port half is design only — not implemented; do not treat as current code behavior.

## Open Questions And Follow-Ups

- Remote-tail feature is in the working tree only — **not committed, not deployed** (deploy = `systemctl restart symphony-host` + journal verify) and not yet live-verified on a real remote run.
- Build the tracker port + Halo adapter (the proposed half): move agent-provisioning behind `adapter.agent_provisioning()`, registry, opaque `tracker_config:`, tunnel-as-inference. Sequenced with the Halo adapter, not before.
- Spool records assistant deltas only (not full tool-call detail) — known ceiling; revisit if remote debugging needs the richer view.
