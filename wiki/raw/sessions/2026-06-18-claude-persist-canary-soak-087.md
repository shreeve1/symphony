# Session Capture: claude_persist canary soak (#087) + steer-queue PrivateTmp fix

- Date: 2026-06-18
- Purpose: Run the manual canary/restart/live soak for ADR-0013 warm Claude sessions on the live `symphony` coding binding (issue #087), the final rollout step. Surfaced and fixed a deployment bug that broke live steering.
- Scope: Live operation on `symphony-host.service` + `podium-api.service`. Captured: soak verdict, evidence log markers, the steer-channel root cause, the unit fix, and bookkeeping.

## Durable Facts

- The soak PASSED on the live `symphony` binding (`claude_persist: true`, committed `ce07042`; `homelab` left unchanged). Podium smoke Issue #45, runs 81/82/83 all `done`. — Evidence: `bindings.yml`, `.kanban/issues/087-MANUAL-canary-restart-soak.md`
- **Warm reattach (AC a):** turn 2 logged `claude_dispatch issue_id=45 resumed=true` then `claude_reattached issue_id=45 socket=/tmp/symphony-claude-persist-symphony-45.sock`, with NO second ready-wait — 2s dispatch→reattach vs 13s for the cold turn 1. — Evidence: `journalctl -u symphony-host.service`, `claude_runner.py`
- **Steer lands next turn (AC b):** after the fix, a Podium steer posted mid-run produced `claude_steer_delivered issue_id=45 kind=steer generation=1`; run-83 result carried the steered line. — Evidence: journal, `web/api/main.py` steer endpoint, `claude_runner.py` poll loop
- **Reap on close (AC c):** moving issue 45 → `done` produced `claude_persist_terminal_reaped issue_id=45 state=done`; the tmux socket and session were removed. — Evidence: journal, `claude_runner.py` `sweep_persistent_claude_sessions`, `scheduler/__init__.py:2375`
- **Deployment bug (root cause):** live steer/abort was accepted (HTTP 200) but never delivered. The steer queue lives at `$SYMPHONY_RUNTIME_DIR/steer` (default `/tmp/symphony/steer`, `web/api/steer_queue.py`). The **writer** `podium-api.service` ran `PrivateTmp=no` (host `/tmp`); the **reader** `symphony-host.service` ran `PrivateTmp=yes` (private namespaced `/tmp`, empty). Neither set `SYMPHONY_RUNTIME_DIR`. So the two never shared the queue dir. Affected pi RPC steering identically. — Evidence: `systemctl show ... -p PrivateTmp`, `nsenter -t <pid> -m ls /tmp/symphony/steer` (empty in service ns; host dir held stale `9.jsonl` + the test `82.jsonl`)
- **Fix:** `Environment=SYMPHONY_RUNTIME_DIR=/run/symphony` drop-in on BOTH `symphony-host.service` and `podium-api.service` (`/etc/systemd/system/<unit>.d/runtime-dir.conf`), `daemon-reload`, restart both. `/run` is not namespaced by `PrivateTmp`, and `/run/symphony` is already shared (holds `symphony.lock` via `RuntimeDirectory=symphony`). AC (b) passed only after this fix. — Evidence: drop-in files (+ `.bak.2026-06-18`), `CLAUDE.md` "Env locations", `docs/adr/0013-warm-claude-session-and-send-keys-steer.md` `soak:` line
- Caveat: symphony-host's `RuntimeDirectoryPreserve=no` wipes `/run/symphony` on its restart; in-flight steer queues are lost and podium-api re-creates the `steer` subdir via `mkdir(exist_ok=True)` on next write.
- Both services restarted clean: `symphony_started code_sha=ce07042 bindings=4`, reconciles 4/4/0, `pi_rpc_probe_ok`, `claude_probe_ok`, `claude_socket_reap_done count=0`, 0 errors.

## Decisions

- Fix the steer path by sharing `SYMPHONY_RUNTIME_DIR=/run/symphony` across both units (James chose this over `PrivateTmp=no`). — Evidence: this session
- ADR-0013 stays `accepted`; its `soak:` line now records the passed soak and the deployment contract. — Evidence: `docs/adr/0013-...md`

## Evidence

- `.kanban/issues/087-MANUAL-canary-restart-soak.md` — soak result section, all ACs ticked.
- `.kanban/issues/086-docs-glossary-wiki.md` — soak result appended to implementation notes.
- `docs/adr/0013-warm-claude-session-and-send-keys-steer.md` — `soak:` frontmatter + deployment-contract consequence bullet.
- `CLAUDE.md`, `~/homelab/docs/runbooks/automation/symphony.md` — `SYMPHONY_RUNTIME_DIR` shared-path requirement + failure pointer.
- `web/api/steer_queue.py` — `steer_queue_dir` resolves `$SYMPHONY_RUNTIME_DIR/steer`.

## Exclusions

- No secret values from `/home/james/symphony-host.env` read or recorded.
- No full transcript captured.

## Open Questions And Follow-Ups

- Consider a startup self-check that warns when the steer queue dir is not writable/visible by both services (the invariant is unit-config-only, unenforced in code).
- Stale host-side `/tmp/symphony/steer/9.jsonl` (pre-fix) can be cleaned up; harmless.
