# Session Capture: podium-api crash-loops with schema-drift 500, fixes installed as auto-migrate systemd unit

- Date: 2026-07-17
- Purpose: capture the failure mode where a pending Alembic migration against the live `podium.db` crashed `podium-api.service` until it was applied; document the auto-heal installed so reboots and post-deploys can no longer leave the API in this state.
- Scope: the crash-loop → 500 path on `/api/auth/login`, the installation of `[email protected]` and the `podium-api.service.d/migrations.conf` drop-in that orders the API after the migration unit, and the tracked `scripts/install-podium-migrations-service.sh` reproducer. Excludes the legitimate `podium-change-password.sh` path (C-0132, still current), and the `ensure_schema` strict-mode policy (preserved unchanged).

## Durable Facts

- Podium authentication already accepts `password` at `POST /api/auth/login` against a bcrypt hash loaded from `PODIUM_PASSWORD_HASH` in `/home/james/symphony-host.env` (C-0065, C-0073). The hash in the env file is stable across reboots — `symphony-host.env` was last modified 2026-07-04, well before the 2026-07-17 outage.
- `podium-api.service`'s lifespan startup calls `ensure_schema(connection)` ([web/api/main.py:534](web/api/main.py#L534)), which raises `RuntimeError("Podium DB schema drift: missing columns …; run `uv run alembic upgrade head` before starting the API")` whenever the SQL columns expected by code do not all exist on the live `podium.db`. Evidenced by `journalctl -u podium-api.service` from 2026-07-17 13:01 onward: `Podium DB schema drift: missing columns ['automation.base_branch', 'automation.preferred_agent', 'automation.preferred_model', 'automation.preferred_skill', 'automation.reasoning_effort', 'automation.worktree_active'] (alembic_version=0022_automation, code expects 0022_automation)`. Restart counter was at 285+ before intervention.
- The drift corresponds to migration `0023_automation_pin_fields` (down_revision=`0022_automation`) which was checked into `web/api/migrations/` but had not been applied against `/home/james/symphony/podium.db`; the DB was sitting at `alembic_version=0022_automation` while `ensure_schema` looked for the six `automation` pin columns added by `0023`.
- `ensure_schema`'s "fail loud, never silently stamp" policy originates from the 2026-06-12 stamp-vs-run drift incident (referenced in `web/api/main.py:540-543`); that policy is preserved by this fix — `ensure_schema` still raises on drift, the auto-heal sits one layer up in the boot ordering.
- `[email protected]` (Type=oneshot, RemainAfterExit=yes) was installed and enabled via `/home/james/symphony/scripts/install-podium-migrations-service.sh`. It calls `/home/james/symphony/.venv/bin/alembic upgrade head` (the project venv's alembic, picked because `systemctl` strips PATH so `uv` at `/home/james/.local/bin/uv` is unreachable from a system service). WorkingDirectory=`/home/james/symphony`; EnvironmentFile=`/home/james/symphony-host.env`. Documented drift snapshot: `wiki/raw/podium-migrations.service`.
- `/etc/systemd/system/podium-api.service.d/migrations.conf` adds `Wants=podium-migrations.service` + `After=podium-migrations.service`, so manual `systemctl start podium-api.service` also pulls the migration unit in. Raw snapshot: `wiki/raw/podium-api.service.d-migrations.conf`.
- Smoke test (transient `_TEMP_smoke_0024.py` migration introduced, then both services restarted via `systemctl start podium-api.service` only): `_TEMP_smoke_0024` was applied automatically, `alembic_version` advanced `0023 → _TEMP_smoke_0024`, the `sim_marker` column landed, `/api/health` and `/api/auth/login` returned 200 and 401 respectively (no 500). The temp file was removed after the smoke.
- Pre-migration DB backup retained at `/home/james/symphony/podium.db.pre023.bak.20260717-131503` (11,436,032 bytes) — same fallback DB path `web.api.db.resolve_db_path()` resolves to.

## Decisions

- **Auto-heal lives in a dedicated `[email protected]`, not in `ensure_schema` and not as `ExecStartPre=` on `podium-api.service`.** Rationale: lets the migration fail and alert independently (`systemctl status podium-migrations.service` is a queryable ops surface), keeps `podium-api` a pure runtime, and avoids the silent-stamp policy regression. Approved by operator 2026-07-17.
- **`podium-migrations.service` does NOT wire `OnFailure=telegram-alert@%n.service`**, because a failed migration propagates as `podium-api` crashing on `ensure_schema`, which already fires the alert via `OnFailure`. Two alerts for one root cause is noise.
- **Strict `ensure_schema` policy is preserved unchanged.** The auto-heal sits one layer up in the boot ordering, not in the schema check.
- **The systemd unit is tracked in the repo as `scripts/install-podium-migrations-service.sh`** rather than living only at `/etc/systemd/system/`. The script is idempotent and prints explicit `systemctl start podium-migrations.service` / `systemctl restart podium-api.service` next steps on first install. Raw live snapshots also stored under `wiki/raw/`.

## Evidence

- `wiki/raw/podium-migrations.service` — live unit snapshot.
- `wiki/raw/podium-api.service.d-migrations.conf` — live drop-in snapshot.
- `web/api/main.py:534-585` — `ensure_schema` (the original "fail loud" guard).
- `web/api/migrations/versions/0023_automation_pin_fields.py` — the migration that was finally applied.
- `scripts/install-podium-migrations-service.sh` — tracked install script.
- `journalctl -u podium-api.service` from 2026-07-17 13:01–13:21, captured above.
- `wiki/analyses/podium-018-auth.md` — adjacent auth analysis (sibling reference, updated with a boot-ordering subsection).

## Exclusions

- No environment values read or printed (`/home/james/symphony-host.env` untouched).
- No session API keys, OAuth tokens, or password hashes captured.
- No raw user pasted content archived.
- `podium-change-password.sh` and `web/cli/podium set-password` were NOT touched (legitimate rotation path still works as documented in C-0132).

## Open Questions And Follow-Ups

- Should future migrations log a "no-op: already at head" line suppression? Currently alembic writes no journal output on no-op (`Finished podium-migrations.service` with no stdout) which is the desired silent-success behavior but makes "did it actually run?" harder to verify from the operator side without `systemctl status`.
- `podium-backup.sh` does not currently coordinate with migrations — a backup taken mid-migration could capture a torn schema. Existing Window: nightly at 02:17, far from boot. Worth re-evaluating only if a future migration proves non-transactional in practice.
- The smoke test that proved the auto-heal was cleaned up by setting `alembic_version=0023_automation_pin_fields` directly; the temp migration file was removed first and the stamp came after. A future cleaner approach would be `alembic downgrade -1` to undo the test migration instead of stamping, but at the time of the smoke the temp revision file was already gone, so stamping was the available safe path.
