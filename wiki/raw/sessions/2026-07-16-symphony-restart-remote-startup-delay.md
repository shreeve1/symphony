# Session Capture: Symphony restart remote startup delay

- Date: 2026-07-16
- Purpose: Safely restart `symphony-host.service` after committing pending harness/handoff changes.
- Scope: Verified scheduler startup timing and healthy lifecycle evidence.

## Durable Facts

- The service restarted successfully as PID `2545958` on code SHA `5c0e8bb`, with seven bindings and no matched error lines after startup. — Evidence: `sudo systemctl restart symphony-host.service`; PID-scoped `sudo journalctl -u symphony-host.service _PID=2545958 --since='2026-07-16 02:56:04' -q`.
- Startup reconciliation began about 148 seconds after `symphony_started`, after `skill_sync_done` and `remote_repo_reachable binding=n8n`; a 90-second lifecycle wait would have falsely looked stalled. — Evidence: same PID-scoped journal: start `02:56:04`, remote reachability `02:57:29`, first `reconcile_startup_begin` `02:58:32`.
- The boot orphan sweep and Pi RPC probe succeeded (`rpc_orphan_reap_done count=0`, `pi_rpc_probe_ok`); seven startup reconciles and run reconciles completed, then dispatch continued. — Evidence: same PID-scoped journal.

## Decisions

- James confirmed the untracked `.claude/.harness-unlock` file is expected local state; it was not committed or removed. — Evidence: operator confirmation in this session.

## Evidence

- `tests/skills/test_restart_troubleshooter.py` — 3 passed after restart.
- `wiki/concepts/symphony-operations.md` — existing restart guidance to update with the observed remote-probe delay.

## Exclusions

- Did not capture `.claude/.harness-unlock` contents, secrets, or unrelated handoff details.
- Did not treat a single restart as a performance guarantee; the timing is an observed lower-bound counterexample to the previous 90-second wait guidance.

## Open Questions And Follow-Ups

- Determine whether remote-binding probe timing should be bounded or separately logged in a future scheduler performance investigation.
