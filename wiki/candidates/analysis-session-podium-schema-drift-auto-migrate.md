---
title: Podium auto-migrate on boot — schema-drift 500 closed at the systemd layer
type: analysis
status: candidate
created: 2026-07-17
updated: 2026-07-17
sources:
  - scripts/install-podium-migrations-service.sh
  - wiki/raw/podium-migrations.service
  - wiki/raw/podium-api.service.d-migrations.conf
  - web/api/main.py
  - web/api/migrations/versions/0023_automation_pin_fields.py
  - wiki/raw/sessions/2026-07-17-podium-schema-drift-auto-migrate.md
confidence: high
tags: [podium, systemd, alembic, migrations, auto-heal, install-script, boot-ordering]
---

# Podium auto-migrate on boot — schema-drift 500 closed at the systemd layer

## Summary

A pending Alembic migration in the tree but never applied against `/home/james/symphony/podium.db` left `podium-api.service` crash-looping at boot. The visible symptom to operators was `POST /api/auth/login` returning HTTP 500 (the service was never up to receive the request), which read as "wrong password" when the failure was actually a schema drift that `ensure_schema` would not let the service start with [source: web/api/main.py] [source: wiki/raw/sessions/2026-07-17-podium-schema-drift-auto-migrate.md].

## Failure Mode (what was happening)

`podium-api.service`'s lifespan startup calls `ensure_schema(connection)` [source: web/api/main.py:534]. When SQL columns expected by code are missing from the live `podium.db`, `ensure_schema` raises `RuntimeError("Podium DB schema drift: missing columns …; run `uv run alembic upgrade head` before starting the API")` and aborts the process. systemd then triggers `OnFailure=telegram-alert@%n.service`, increments the restart counter, and tries again — forever — until the drift is resolved [source: web/api/main.py] [source: wiki/raw/sessions/2026-07-17-podium-schema-drift-auto-migrate.md].

The 2026-07-17 incident specifically: migration `0023_automation_pin_fields` was checked into `web/api/migrations/` but never applied. `alembic_version` was `0022_automation` on the live DB while code expected the six pin columns added by `0023`. The journal showed restart counter at 285+ before intervention; the password hash in `/home/james/symphony-host.env` (C-0065) was unchanged the whole time [source: wiki/raw/sessions/2026-07-17-podium-schema-drift-auto-migrate.md] [source: web/api/migrations/versions/0023_automation_pin_fields.py].

## Auto-Heal Design

A dedicated oneshot systemd unit runs `alembic upgrade head` before `podium-api.service` starts, ordered by systemd's `Before=` / `After=` mechanism. The unit is enabled, idempotent across reboots, and explicitly does not embed auto-migrate logic inside the Python startup path so the strict "fail loud, never silently stamp" policy from the 2026-06-12 stamp-vs-run drift incident stays in force [source: web/api/main.py:540-543] [source: wiki/raw/podium-migrations.service].

### Unit topology

- `[email protected]` ([wiki/raw/podium-migrations.service](/wiki/raw/podium-migrations.service)) — `Type=oneshot`, `RemainAfterExit=yes`. Calls `/home/james/symphony/.venv/bin/alembic upgrade head` directly (systemctl strips PATH so `uv` at `/home/james/.local/bin/uv` is unreachable; the venv-resident `alembic` script invokes the right Python interpreter). `WorkingDirectory=/home/james/symphony`, `EnvironmentFile=/home/james/symphony-host.env`. `Before=podium-api.service`. `After=network.target` (no other ordering deps). `WantedBy=multi-user.target`.
- `/etc/systemd/system/podium-api.service.d/migrations.conf` ([wiki/raw/podium-api.service.d-migrations.conf](/wiki/raw/podium-api.service.d-migrations.conf)) — drop-in that adds `Wants=podium-migrations.service` and `After=podium-migrations.service`. Lets a manual `systemctl start podium-api.service` also pull the migration unit in (covers the case where the API was never enabled but is being started ad hoc).
- `podium-migrations.service` deliberately does NOT wire `OnFailure=telegram-alert@%n.service`; a failed migration propagates as `podium-api` crashing on `ensure_schema`, which already fires the existing alert via `OnFailure`. Two alerts for one root cause would be noise [source: wiki/raw/podium-migrations.service].

### Why a oneshot unit (and not `ExecStartPre=`)

Visibility. `systemctl status podium-migrations.service` is a single ops surface: when did it last run, what was its last exit code, what was its last completion time. With `ExecStartPre=` baked into `podium-api.service`, a migration failure interleaves with the API crash in one stream of journal entries and the operator has to read both. The dedicated unit also gives a future cron-style "run `alembic upgrade head` on demand" path via `systemctl start podium-migrations.service` [source: wiki/raw/podium-migrations.service] [source: wiki/raw/sessions/2026-07-17-podium-schema-drift-auto-migrate.md].

### Why not relax `ensure_schema`

The 2026-06-12 stamp-vs-run drift incident shaped the policy expressed at [source: web/api/main.py:540-543]: never stamp a schema over a known-wrong alembic_version. The auto-heal lives one layer up — the boot graph, not the schema check. `ensure_schema` still raises on drift, so the existing 401/500 ops surface is unchanged for cases where the drift is real and dangerous; the difference is that drift is now auto-applied before the API tries to start, so the API never enters the crash-loop state in the first place [source: web/api/main.py].

## Tracked install script

The systemd unit content lives as a bash heredoc in `scripts/install-podium-migrations-service.sh`, which `tee`s both files into place, runs `systemctl daemon-reload`, and `systemctl enable podium-migrations.service`. The script is idempotent (re-running reconverges the units without restarting any service), `set -euo pipefail`, requires `id -u == 0`, and exits non-zero if the alembic binary is absent. This keeps the repo as the source of truth for what `/etc/systemd/system/` holds, matching the precedent set by `scripts/podium-change-password.sh` (C-0132) and `scripts/podium-backup.sh` [source: scripts/install-podium-migrations-service.sh] [source: scripts/podium-change-password.sh] [source: scripts/podium-backup.sh].

## Smoke Verification

A transient `_TEMP_smoke_0024.py` migration was introduced, then both services were restarted via `systemctl start podium-api.service` only. `podium-migrations.service` auto-pulled via `Wants=`, alembic advanced `0023 → _TEMP_smoke_0024`, the `sim_marker` column landed, `/api/health` returned 200 and `/api/auth/login` returned 401 (no 500). The temp file was then removed and `alembic_version` stamped back to `0023_automation_pin_fields` (an alternative, less-risky cleanup would be `alembic downgrade -1` if the temp revision file is still on disk) [source: wiki/raw/sessions/2026-07-17-podium-schema-drift-auto-migrate.md].

## Out of Scope (carried as follow-ups)

- A future migration with a non-zero expected downtime would want a `podium-migrations.service` `TimeoutStartSec=` escalation or a migration-specific unit per migration. Not added pre-emptively.
- `podium-backup.sh` (cron-daily 02:17) does not currently coordinate with migrations; a backup taken mid-migration could capture a torn schema. Today's window is far from boot (nightly), so the practical risk is small. Worth revisiting only if a future migration proves non-transactional.
- The `podium-migrations.service` journal is silent on the no-op path (alembic writes nothing when at head). An operator who wants to verify "did migrations run?" reads `systemctl status podium-migrations.service` (Result / Exit Code / Activated timestamps), not the journal. This is the desired silent-success behavior but could be surprising.

## Citations

- Raw session: [wiki/raw/sessions/2026-07-17-podium-schema-drift-auto-migrate.md](/wiki/raw/sessions/2026-07-17-podium-schema-drift-auto-migrate.md) — session capture with journal evidence and decision rationale.
- Unit snapshot: [wiki/raw/podium-migrations.service](/wiki/raw/podium-migrations.service) — live `podium-migrations.service` from `/etc/systemd/system/`.
- Drop-in snapshot: [wiki/raw/podium-api.service.d-migrations.conf](/wiki/raw/podium-api.service.d-migrations.conf) — live drop-in from `/etc/systemd/system/podium-api.service.d/`.
- Install script: [scripts/install-podium-migrations-service.sh](/home/james/symphony/scripts/install-podium-migrations-service.sh) — idempotent installer (absolute on-disk path).
- `ensure_schema`: [web/api/main.py](/home/james/symphony/web/api/main.py#L534) — strict-mode guard preserved unchanged.
- Trigger migration: [web/api/migrations/versions/0023_automation_pin_fields.py](/home/james/symphony/web/api/migrations/versions/0023_automation_pin_fields.py) — pending migration that never reached the live DB until the auto-heal.
- Sibling analysis: [wiki/analyses/podium-018-auth.md](/wiki/analyses/podium-018-auth.md) — adjacent auth analysis (boot-ordering subsection appended in this session).
- Systemd catalog: [wiki/sources/podium-systemd-units.md](/wiki/sources/podium-systemd-units.md) — extended in this session to list `[email protected]` alongside the existing `podium-api.service` / `podium-web.service` / `telegram-alert@.service`.
- Smoke evidence: `journalctl -u podium-api.service` 2026-07-17 13:01–13:21 (captured in the raw session note above).
