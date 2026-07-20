# Session Capture: Podium startup model probe decoupling

- Date: 2026-07-20
- Purpose: Prevent a default Pi provider quota cooldown from disabling otherwise dispatchable Podium bindings.
- Scope: Incident diagnosis, policy correction, code fix, and regression evidence.

## Durable Facts

- At the 2026-07-19 22:00 UTC scheduler start, the per-binding `pi-duo/Duo` print probe timed out and `symphony` plus `pi-rmm` logged `binding_skipped_after_probe_failure`; their scheduler loops never started. — Evidence: `journalctl -u symphony-host.service --since '2026-07-19 22:00:00' --until '2026-07-19 22:09:00'`.
- Podium issues 549 (`symphony`) and 546/548 (`pi-rmm`) were otherwise dispatch candidates: no unmet dependency, lock, hold, schedule, approval, or retry-cooldown gate. — Evidence: read-only `podium.db` inspection plus `PodiumTrackerAdapter.list_candidates()` with a query-only connection.
- `main._probe_binding` now skips the provider/model print probe for Podium bindings; local non-Podium Pi bindings retain the bounded legacy probe. — Evidence: `main.py`; `tests/test_main.py::test_probe_binding_podium_skips_default_model_probe`.
- `main.run_bindings_loop` still performs the model-independent Pi RPC capability probe when any binding uses `pi_mode: rpc`; Podium model resolution and validation remain per-Issue dispatch gates. — Evidence: `main.py`; `scheduler/__init__.py`; `scheduler/tick.py`.

## Decisions

- A default model provider's quota or availability must not decide whether a Podium binding starts. Podium model failures are scoped to the Issue that selected that model. — Evidence: operator direction in this session; implemented in `main.py`.
- ADR-0026's bounded/fail-soft startup provider probe remains historical behavior for Podium and is amended rather than reintroduced; its terminal retry and auto-land decisions remain unchanged. — Evidence: `docs/adr/0026-transient-failure-retry-not-block.md`; `main.py`.

## Evidence

- `main.py` — tracker-scoped startup probe behavior.
- `tests/test_main.py` — regression proving Podium does not call `verify_pi_support` at startup.
- `tests/test_agent_runner.py` — legacy non-Podium bounded probe coverage remains.
- `uv run pytest -q tests/test_main.py tests/test_agent_runner.py` — 72 passed, 1 skipped.
- Independent read-only verifier — both load-bearing code claims returned VERIFIED.

## Exclusions

- No credentials, environment-file contents, provider tokens, or raw private issue content were captured.
- No service restart, DB write, Issue mutation, or model-catalog change is part of this capture.

## Open Questions And Follow-Ups

- Restart `symphony-host.service` after the code is committed so skipped bindings are rebuilt under the corrected policy.
