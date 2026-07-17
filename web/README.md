# Podium web stack

Podium is Symphony's native operator console. Issue `012a` adds the backend API; `012b` adds the frontend shell under `web/frontend/`.

## API dev loop

From the repository root:

```bash
cd web/api
uvicorn main:app --host 127.0.0.1 --port 8090
```

Bind to `127.0.0.1` only. External access is handled by the Authelia gate — see *Reverse proxy* below.

Health check:

```bash
curl -s http://localhost:8090/api/health
```

## Change Podium password

Use the helper from the repository root:

```bash
cd /home/james/symphony
scripts/podium-change-password.sh
```

The helper runs the shared-password CLI, prints a new `PODIUM_PASSWORD_HASH=...`
line, then prints the required operator steps. It does not edit secrets and does
not restart services.

Manual equivalent:

```bash
cd /home/james/symphony
uv run python -m web.cli.podium set-password
sudoedit /home/james/symphony-host.env
sudo systemctl restart podium-api.service
systemctl status podium-api.service --no-pager
curl -s http://127.0.0.1:8090/api/health
```

Replace only `PODIUM_PASSWORD_HASH=...` in `/home/james/symphony-host.env`.
Restarting `podium-api.service` is enough; `podium-web.service` does not validate
passwords.

Existing browser sessions remain valid after changing only the password hash. To
force everyone to log in again, also rotate `PODIUM_SESSION_SECRET` in the same
env file with a new value from:

```bash
openssl rand -hex 32
```

Then restart `podium-api.service`.

## SQLite path

Default database path is:

```text
/var/lib/symphony/podium.db
```

The operator should pre-create the parent directory when running on the host:

```bash
sudo install -d -o james -g james /var/lib/symphony
```

Do not run that command from automation without explicit operator approval. If `/var/lib/symphony/` does not exist or is not writable, the API falls back to:

```text
./podium.db
```

where `.` is the repository root. For tests or local overrides, set:

```bash
export PODIUM_DB_PATH=/path/to/podium.db
```

Run log paths stored in the database are absolute and co-located with the active database:

```text
<active-podium-db-parent>/runs/
```

On the host default path, that resolves to `/var/lib/symphony/runs/`. When the API falls back to `./podium.db`, run logs fall back to `./runs/` too.

## Binding tracker rollback

The `trading` and `homelab` bindings are cut over by declaring
`tracker: podium` in `bindings.yml`. To roll a binding back to Plane,
remove that binding's `tracker: podium` line, uncomment its Plane rollback
`tracker_contract` block if present, and restart the scheduler after explicit
operator approval:

```bash
sudo systemctl restart symphony-host.service
```

Rollback availability per binding:

- **homelab** — rollback still available; its Plane `tracker_contract` block
  remains commented in `bindings.yml` and its Plane project is still active.
- **trading** — rollback **retired** (#023d, 2026-06-11). The Plane project was
  archived and the `tracker_contract` block removed from `bindings.yml`, so the
  binding now falls back to `DEFAULT_CONTRACT`. Re-establishing Plane rollback
  for trading would require unarchiving the Plane project and restoring the
  contract block.

## Migrations

Initial schema lives under `web/api/migrations/` and is driven by the root `alembic.ini`. As of 2026-07-17, every OS reboot and every `systemctl start podium-api.service` invocation also runs `alembic upgrade head` automatically via `[email protected]` (a oneshot unit ordered `Before=podium-api.service`); the unit and its drop-in are installed idempotently by `scripts/install-podium-migrations-service.sh`. The strict `ensure_schema` "fail loud, never silently stamp" guard at the Python startup (`web/api/main.py:534`) is preserved unchanged; the auto-heal sits one layer up in the boot graph.

A failed migration leaves the unit in `failed` state and propagates as `podium-api.service` crash-looping on `ensure_schema` — the existing `OnFailure=telegram-alert@%n.service` alert fires. Recovery is operator-initiated (`systemctl reset-failed podium-migrations.service && systemctl start podium-migrations.service`, then `systemctl restart podium-api.service`).

Manual `alembic upgrade head` is still required against a fresh fallback DB outside the boot path (e.g., after a destructive restore):

```bash
cd /home/james/symphony
alembic upgrade head
```

Schema changes must ship as new Alembic revisions, never by editing prior revisions. Validate the baseline before merging schema changes:

```bash
cd /home/james/symphony
uv run pytest tests/test_alembic_baseline.py
```

## Reset local DB

For the repo-root fallback database:

```bash
rm -f podium.db
cd web/api
uvicorn main:app --host 127.0.0.1 --port 8090
```

Startup creates tables when needed and seeds an empty database from `bindings.yml`.

For a custom database:

```bash
rm -f "$PODIUM_DB_PATH"
cd /home/james/symphony
alembic upgrade head
```

## Backup

Podium's single-host SQLite store and run logs are backed up by the host cron job in `/etc/cron.d/podium-backup`. The job runs `scripts/podium-backup.sh` daily as `james`, writes database snapshots to `/backup/podium-YYYY-MM-DD.db`, archives run logs to `/backup/podium-runs-YYYY-MM-DD.tar.gz` when a runs directory exists, and deletes Podium backup artifacts older than 14 days.

The script resolves the active database path through `web.api.db.resolve_db_path()`: `/var/lib/symphony/podium.db` when `/var/lib/symphony/` is writable, otherwise the repo-root fallback `./podium.db`. The single-host posture is intentional for v1: there is no off-host replication, so host loss can still lose both the live database and local backups.

Manual backup drill:

```bash
cd /home/james/symphony
scripts/podium-backup.sh
ls -la /backup/podium-*.db
```

Restore procedure:

```bash
sudo systemctl stop podium-api.service podium-web.service
cp /path/to/restored-podium.db /var/lib/symphony/podium.db
sudo chown james:james /var/lib/symphony/podium.db
sudo systemctl start podium-api.service podium-web.service
```

If Podium is using the repo-root fallback, restore to `/home/james/symphony/podium.db` instead of `/var/lib/symphony/podium.db` and preserve `james:james` ownership.

## Frontend dev loop

The frontend (Next.js App Router) lives under `web/frontend/` and listens on
`127.0.0.1:8091`. It proxies `/api/*` to the backend on `127.0.0.1:8090` via a
Next rewrite, so start the API first (see *API dev loop* above).

```bash
cd web/frontend
pnpm install
pnpm dev          # next dev -H 127.0.0.1 -p 8091
```

Then open http://localhost:8091/. Override the backend origin with
`PODIUM_API_ORIGIN` if it is not on `127.0.0.1:8090`.

## Reverse proxy

External access is served at `https://podium.testytech.net` through the existing
Authelia gate on port `9091`, mirroring the pattern used for the other internal
services on this host.
Authelia is an auth middleware in front of the reverse proxy; the proxy
terminates the public route, forwards an auth subrequest to Authelia, and on
success proxies through to the Podium frontend.

The reverse proxy reaches the frontend at the host's LAN address
`10.20.20.16:8091` (not loopback). **Bind-address requirement:** by default the
frontend listens on `127.0.0.1:8091` only (`podium-web.service` `HOST=127.0.0.1`),
which a proxy targeting `10.20.20.16:8091` cannot reach. The operator must set
the frontend to listen on the LAN interface — e.g. `HOST=10.20.20.16` (or
`0.0.0.0`) on `podium-web.service`, then `daemon-reload` + restart that unit.
Note this exposes the raw port `8091` on the `10.20.20.16` network; the Authelia
gate remains the only intended entry point, but the unauthenticated port becomes
reachable to LAN hosts. Restrict with a host firewall rule if that is a concern.

This is operator-side infrastructure outside this repo. Symphony does not edit
Authelia, the reverse proxy, or the `podium-web.service` unit. The snippet below
is the rule to add; adapt host names and the proxy syntax to whatever the other
internal services already use.

Authelia access-control rule (`configuration.yml` `access_control.rules`):

```yaml
access_control:
  rules:
    # Podium operator console — same one_factor/two_factor policy as the
    # other internal services on this host.
    - domain: podium.testytech.net
      policy: two_factor
```

Reverse-proxy route (forward-auth to Authelia on `9091`, upstream Podium on
`10.20.20.16:8091`) — shown as an nginx `location`; translate to the host's
actual proxy (Traefik labels, Caddy, etc.) to match the existing services:

```nginx
server_name podium.testytech.net;

location / {
    # Authelia forward-auth subrequest
    auth_request /authelia;
    # Authelia portal FQDN — confirm against the existing services' value.
    error_page 401 =302 https://auth.testytech.net/;

    proxy_pass http://10.20.20.16:8091;
    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location = /authelia {
    internal;
    proxy_pass http://127.0.0.1:9091/api/verify;
    proxy_set_header X-Original-URL    $scheme://$host$request_uri;
}
```

After the operator applies this and reloads the proxy, confirm Podium is
reachable through the Authelia gate at the documented URL.

## Skill catalog

The `skill` table is owned by the operator-run refresh CLI, not startup
seeding. Populate or refresh it after deploys and after editing local skills:

```bash
cd /home/james/symphony
python -m web.cli.podium skills refresh
```

Dry-run mode lists the scanned catalog rows without touching the database:

```bash
python -m web.cli.podium skills refresh --dry-run
```

Until the refresh runs, skill dropdowns show:

```text
Run `podium skills refresh` to populate.
```

## Frontend e2e tests

Playwright spins up both servers itself on isolated ports (`uv run uvicorn` on
18090 and `next dev` on 18091), so no servers need to be running first. Browser
binaries must be installed once:

```bash
cd web/frontend
pnpm exec playwright install chromium
pnpm test:e2e
```

The suite uses an isolated throwaway SQLite database at
`web/frontend/test-results/podium-e2e.db` via `PODIUM_DB_PATH`; it does not
write to `/var/lib/symphony/podium.db` or the repo-root fallback DB. Playwright
removes and recreates that e2e DB at the start of each run, then test helpers
insert any skills needed by the specs.

## Tests

```bash
cd /home/james/symphony
uv run pytest
```
