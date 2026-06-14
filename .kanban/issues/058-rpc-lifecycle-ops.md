---
id: 058
title: pi RPC lifecycle & ops (orphan reaping, timeout, concurrency) — Slice E
status: review
blocked_by: [050]
parent: null
priority: 0
created: 2026-06-13
updated: 2026-06-14
actor: ralph
---

## PARTIAL 2026-06-14 — orphan-reaper + startup probe landed (commit 44e72c9)

Done as the gate for enabling `pi_mode: rpc` on real bindings (all three flipped 2026-06-14, C-0191):
- **Orphan reaping** — `reap_orphan_rpc_processes()` (boot sweep wired into `run_bindings_loop` beside `reap_orphan_claude_sockets`) SIGKILLs leftover `pi --mode rpc` processes; `run_pi_rpc_agent` writes/removes `<runtime>/rpc/<pid>.pid`, guarded on `/proc/<pid>/stat` start-time (pi masks argv; pid-reuse safe). Uses SIGKILL because pi `--mode rpc` ignores SIGTERM.
- **Startup probe** — `verify_pi_rpc_support()` (boot `get_state` probe), run when any binding is rpc; logs `pi_rpc_probe_ok`/`pi_rpc_probe_failed`.
- **Run timeout** — already enforced by #050's adapter (deadline → abort → `timed_out`).

Still TODO here: **concurrency-cap accounting** is already satisfied structurally (RPC dispatch is synchronous inside the semaphore slot) but lacks an explicit asserting test; **steer-queue cleanup** is deferred to #056 (no steer channel yet). Keep this issue open for those.

## What to build

Operational hardening for long-lived `pi --mode rpc` processes — the RPC analogue of the Claude tmux socket reaper/probe (`reap_orphan_claude_sockets`, `verify_claude_support`). Until this lands, RPC dispatch stays on the throwaway test binding only.

- **Run timeout across the pump loop:** enforce `run_timeout_ms` while pumping events — a wall-clock breach sends RPC `abort`, drains, and returns `AgentResult(timed_out=True)`. A model that streams forever or stalls between events must not hang the dispatch tick.
- **Orphan reaping:** a startup sweep (analogue of the socket reaper) that kills `pi --mode rpc` processes / clears steer queues left by a prior scheduler crash; the run reaper already fails their Run rows, so adopt nothing — just clean up.
- **Concurrency cap:** ensure live RPC processes count against the existing global Run concurrency cap exactly as one-shot/tmux runs do; no unbounded fan-out of held processes.
- **Startup probe:** a lightweight `verify_pi_rpc_support` (analogue of `verify_pi_support`) — `pi --mode rpc` launches and answers a no-LLM `get_state`/`get_commands` under the service env — surfacing a broken RPC binary at boot, not on first dispatch.
- **Steer-queue cleanup:** per-run queue files/keys removed on run completion or abort; restart-safe.

## Acceptance criteria

- [ ] A run exceeding `run_timeout_ms` (including a between-events stall) is aborted and returns `timed_out=True`; no hung tick.
- [ ] Startup sweep kills orphan RPC processes and clears stale steer queues; idempotent; logs a count like the socket reaper.
- [ ] Live RPC runs are counted by the global concurrency cap (test asserts the cap blocks an over-limit dispatch).
- [ ] `verify_pi_rpc_support` runs at boot when any binding is RPC-enabled and records a probe-failure reason without failing scheduler boot (mirrors `claude_probe_failed`).
- [ ] Steer queues are cleaned on completion/abort and on restart.

## Verification

`uv run pytest tests/test_agent_runner*.py tests/test_scheduler*.py tests/test_main*.py -q`

## Blocked by

- Blocked by #050
