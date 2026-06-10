# Podium web stack

Podium is Symphony's native operator console. Issue `012a` adds the backend API only.

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

Run log paths stored in the database are absolute and rooted at:

```text
/var/lib/symphony/runs/
```

## Migrations

Initial schema lives under `web/api/migrations/` and is driven by the root `alembic.ini`.

```bash
cd /home/james/symphony
alembic upgrade head
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

## Tests

```bash
cd /home/james/symphony
uv run pytest
```
