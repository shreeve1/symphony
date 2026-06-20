# Session Capture: SYMPHONY_RUN_CAP reduced 3 → 2 (per-binding concurrency)

- Date: 2026-06-20
- Purpose: Operator wanted to reduce simultaneous pi agents per binding to 2.
- Scope: Live config value change + reaffirmation of the per-binding (not per-host) cap model.

## Durable Facts

- The live `SYMPHONY_RUN_CAP` value is now `2` (was `3`). Set in the systemd drop-in `/etc/systemd/system/symphony-host.service.d/override.conf` (`Environment=SYMPHONY_RUN_CAP=2`). — Evidence: `systemctl show symphony-host.service -p Environment` → `SYMPHONY_RUN_CAP=2`; service re-`active` with `symphony_started ... bindings=5` after `daemon-reload` + `restart`.
- `bindings.yml` carries **no** concurrency knob; the cap is the single env var `SYMPHONY_RUN_CAP` applied per binding (`config.py:176` default `2`, `config.py:294` env read). — Evidence: `bindings.yml`, `config.py:176,294`.
- The cap is **per-binding, not per-host**: host-wide ceiling ≈ `run_cap × num_bindings`; remote bindings clamp to 1 (`_effective_run_cap`). With 5 bindings (n8n remote) the ceiling at cap=2 is ~9. Already documented in C-0251 / ADR-0012; unchanged by this session. — Evidence: `scheduler/__init__.py:161-193`.

## Decisions

- Reduce per-binding pi concurrency to 2 (`SYMPHONY_RUN_CAP=2`). Operator clarified intent is "2 per binding," not a true host-wide total of 2 (which would need a shared global semaphore — not built). — Evidence: this session.

## Evidence

- `/etc/systemd/system/symphony-host.service.d/override.conf` — holds the live `SYMPHONY_RUN_CAP` value.
- `config.py:176,294` — default and env read.
- `scheduler/__init__.py:161-193` — per-binding semaphore + remote clamp.

## Exclusions

- No secrets read or written; the env file `/home/james/symphony-host.env` was not modified (RUN_CAP lives in the drop-in, not the secrets bag).

## Open Questions And Follow-Ups

- A true host-wide cap (e.g. exactly 2 across all bindings) is not achievable by config alone; it would require a shared semaphore wrapping all bindings in `run_bindings_loop`. Deferred — not requested.
