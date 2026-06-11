# Podium database migrations

Podium uses Alembic for SQLite schema changes. The checked-in migration history is intentionally linear.

## Rules

- Schema changes ship as a new revision, never an edited prior revision.
- Keep `web/api/schema.py::SCHEMA_SQL` in sync with Alembic migrations so the runtime boot path and `alembic upgrade head` create the same schema.
- Before merging schema changes, run the baseline verification:

```bash
cd /home/james/symphony
uv run pytest tests/test_alembic_baseline.py
```

That test upgrades a fresh SQLite database to Alembic head and compares it with the runtime schema created from `SCHEMA_SQL`.
