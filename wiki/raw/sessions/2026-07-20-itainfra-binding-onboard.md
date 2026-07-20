# Session Capture: itainfra Binding Onboard

- Date: 2026-07-20
- Purpose: Record the live onboarding and smoke verification of the remote `itainfra` Podium binding.
- Scope: Binding configuration, scheduler reload, smoke result, and verification evidence only.

## Durable Facts

- `itainfra` is a remote Podium coding binding for `/home/itadmin/itainfra` on `main`, dispatched as Pi RPC over SSH to `itadmin@100.95.224.218`; `remote.host_alias: n8n` groups it with the existing n8n-host bindings. — Evidence: `bindings.yml`, commit `fe6ffd2`.
- The target repository exists on the remote host, is on `main`, and has a top-level `CLAUDE.md`. — Evidence: batch-mode SSH preflight during onboarding.
- The live Podium database contains active `binding` and `binding_settings` rows for `itainfra`. — Evidence: `SELECT` checks through `web.api.db.resolve_db_path()` after scaffold.
- `symphony-host.service` restarted as PID `2299168` on code SHA `9675c6e` with ten bindings; startup logged `pi_rpc_probe_ok`, `reconcile_startup_done binding=itainfra cleaned=0`, and a live `dispatch_completed` cycle with no matched errors. — Evidence: PID-scoped `journalctl` verification after the scheduler-only restart.
- Smoke Issue `554` ran once as Run `3237` with `auto_land=false`; the Run used `pi` / `pi-duo` / `Duo:high`, exited `0`, succeeded with verdict `done`, and left the Issue in `in_review`. — Evidence: live Podium Issue/Run rows and `runs/3237.log`.

## Decisions

- The omitted binding type resolved to `coding`, because remote Pi RPC bindings require coding mode; the `itainfra` name does not select infra behavior. `symphony-workflow-author` was therefore skipped. — Evidence: `.claude/skills/symphony-binding-scaffold/SKILL.md`, onboarding workflow.
- The scaffold reused the existing n8n host grouping alias instead of creating a separate sidebar host. — Evidence: `bindings.yml`.

## Evidence

- `bindings.yml` — committed remote binding configuration.
- `fe6ffd2` — Symphony commit adding the binding.
- `runs/3237.log` — smoke agent terminal result.
- `tests/skills/test_binding_scaffold.py` — 10 passed.
- `tests/skills/test_binding_smoke.py` — 2 passed.
- `tests/skills/test_onboard_project.py` — 1 passed.

## Exclusions

- No environment file, credential, SSH key, provider secret, session cookie, or authentication-store content was read or captured.
- Routine command output and the full conversation were not archived.

## Open Questions And Follow-Ups

- None. The operator-created smoke Issue intentionally remains in `in_review` as audit evidence.
