---
id: 044
title: Claude startup probe + orphan tmux socket reaper
status: review
blocked_by: [042, 043]
parent: null
priority: 2
created: 2026-06-13
updated: 2026-06-13
actor: ralph
---

## What to build

Startup hardening for the claude engine, per the ADR-0001 amendment (`docs/adr/0001-claude-via-tmux-send-keys.md`).

1. **`verify_claude_support`** (in `claude_runner.py`, analogue of `verify_pi_support`): checks that `tmux` and the claude binary resolve under the service environment and that `claude --version` exits 0 within a bounded timeout (injectable `run_func`, same style as `verify_pi_support`). Runs once at startup. **On failure it must NOT fail boot** (pi-only operation survives a missing/broken claude install — deliberate divergence from the pi probe): log a loud structured line (`claude_probe_failed reason=...`) and set a module/config-level flag the dispatch gate consults, so claude dispatches block with "Dispatch blocked: claude engine probe failed at startup: <reason>. Fix the install and restart." Pi dispatches are unaffected. No live claude session is launched and no tokens are spent by the probe.
2. **Orphan socket reaper**: at startup, before the per-binding reconcile loop and exactly once globally (not per binding), glob `/tmp/symphony-claude-*.sock`; for each survivor run `tmux -S <socket> kill-server` (ignore failures — server may already be gone) and remove the socket file. Log one structured line per reaped socket (`claude_socket_reaped path=...`) and a summary count. Orphaned Run rows are already failed by the existing run reaper (#022) — this slice only kills the tmux survivors so they stop burning tokens.
3. Wire both into the startup path in `main.py` next to the existing `verify_pi_support` / reconcile calls. The reaper runs regardless of probe outcome.

## Acceptance criteria

- [ ] Probe success path: fake `run_func` returning 0 for `claude --version` → flag clear, claude dispatch gate passes (with #043 wiring).
- [ ] Probe failure paths (binary missing → OSError; non-zero exit; timeout): startup completes without raising, loud log emitted, subsequent claude dispatch blocks with the probe-failure message, pi dispatch unaffected.
- [ ] Reaper test with fake glob + fake tmux runner: two stale sockets → two kill-server invocations + both socket files removed + summary log; zero sockets → no tmux calls; kill-server failure on one socket does not abort reaping the other.
- [ ] Reaper invoked exactly once per process start (not once per binding) — assert call count with two bindings configured.
- [ ] `uv run pytest` green.

## Verification

`uv run pytest`

## Blocked by

- Blocked by #042
- Blocked by #043
