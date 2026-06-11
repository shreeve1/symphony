# Podium web stack

Podium is Symphony's native operator console. Issue `012a` adds the backend API; `012b` adds the frontend shell under `web/frontend/`.

## API dev loop

From the repository root:

```bash
cd web/api
uvicorn main:app --host 127.0.0.1 --port 8090
```

Bind to `127.0.0.1` only. External access will be handled by the later reverse-proxy slice.

Health check:

```bash
curl -s http://localhost:8090/api/health
```

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
`tracker: podium` in `bindings.yml`. To roll either binding back to Plane,
remove that binding's `tracker: podium` line, uncomment its Plane rollback
`tracker_contract` block if present, and restart the scheduler after explicit
operator approval:

```bash
sudo systemctl restart symphony-host.service
```

The commented Plane tracker contract blocks remain in `bindings.yml` for this
rollback path until the later Plane archive slice.

## Migrations

Initial schema lives under `web/api/migrations/` and is driven by the root `alembic.ini`.

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
