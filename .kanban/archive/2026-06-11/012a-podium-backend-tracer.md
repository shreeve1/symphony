---
id: 012a
title: Podium backend tracer — FastAPI + SQLite + Alembic + seed + read endpoints
status: done
blocked_by: []
parent: null
priority: 0
created: 2026-06-10
---

## What to build

The backend half of the Podium tracer bullet. No frontend yet.

Per ADR-0005 (`docs/adr/0005-replace-plane-with-podium.md`):

- FastAPI app at `web/api/`, runnable via `uvicorn main:app --host 127.0.0.1 --port 8090`.
- Store: SQLite at `/var/lib/symphony/podium.db` (operator pre-creates
  `/var/lib/symphony/` with `sudo install -d -o james -g james` — ask James
  before running sudo; if the path is not writable, fall back to
  `./podium.db` under repo root and document the override in `web/README.md`).
- Run logs base path: `/var/lib/symphony/runs/` — every `runs/{id}.log`
  reference in other slices is resolved against this absolute root.

Schema (Alembic initial revision under `web/api/migrations/`, all tables):

```
binding(
  name TEXT PK,
  display_name TEXT,
  color TEXT DEFAULT '#888888',
  sort_order INTEGER,
  archived BOOLEAN DEFAULT FALSE
)

issue(
  id INTEGER PK,
  binding_name TEXT FK,
  title TEXT,
  description TEXT,
  state TEXT NOT NULL,             -- enum: 'todo','in_review','running','blocked','done'
  priority TEXT,                   -- enum: 'low','med','high','urgent'
  preferred_agent TEXT,            -- 'pi' for now
  preferred_model TEXT,
  preferred_skill TEXT,            -- FK by name to skill.name
  reasoning_effort TEXT DEFAULT 'high',
  worktree_active BOOLEAN DEFAULT FALSE,
  max_duration_seconds INTEGER,
  base_branch TEXT,
  comments_md TEXT DEFAULT '',
  context_md TEXT DEFAULT '',
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  latest_run_id INTEGER FK,
  latest_verdict TEXT,             -- enum: 'done','review','blocked'
  latest_run_state TEXT,           -- mirrors run.state enum below
  last_event_at TIMESTAMP
)

run(
  id INTEGER PK,
  issue_id INTEGER FK,
  agent TEXT,
  provider TEXT,
  model TEXT,
  state TEXT NOT NULL,             -- enum: 'queued','running','succeeded','failed'
  verdict TEXT,                    -- enum: 'done','review','blocked' (NULL while running)
  summary TEXT,
  exit_code INTEGER,
  cost_usd NUMERIC,
  input_tokens INTEGER,
  output_tokens INTEGER,
  worktree_path TEXT,
  branch_name TEXT,
  base_branch TEXT,
  log_path TEXT,                   -- absolute, /var/lib/symphony/runs/{id}.log
  skill_invoked TEXT,
  started_at TIMESTAMP,
  ended_at TIMESTAMP
)

skill(                              -- catalog table, ships empty; seeded by #015 CLI
  name TEXT PK,
  description TEXT,
  source TEXT
)
```

**Run state enum is the canonical four-value set `{queued, running, succeeded, failed}`** —
referenced by every downstream slice. A "succeeded" run carries a non-null
`verdict` (`done` / `review` / `blocked`); a "failed" run carries a null
verdict (or an engine-synthesized one — see #022 for the reaper).

Seed routine (`web/api/seed.py`) populates the DB on startup if empty:

- Both bindings from `bindings.yml` (read at startup, projected into
  `binding` rows with `sort_order` = index in YAML, `display_name` = name,
  `color` = `#888888`, `archived` = false).
- Two fake `issue` rows per binding, one Todo and one Running, with
  realistic `comments_md` and `context_md` blobs.
- One fake `run` row per issue (state = `succeeded`, verdict = `review`).
- `skill` table left empty (populated by #015's CLI).

Endpoints (read-only):

- `GET /api/health` → `{"status": "ok"}` — no auth ever required (#018 leaves this exempt).
- `GET /api/bindings` → list bindings.
- `GET /api/bindings/{name}/issues` → list issues for a binding.
- `GET /api/issues/{id}` → single issue with `comments_md` and `context_md`.
- `GET /api/issues/{id}/runs` → run history for an issue.

Pytest config: extend root `pyproject.toml` `[tool.pytest.ini_options]`
`testpaths` to include `web/api/tests` and `pythonpath` to include
`web/api`. Do NOT create a second `pyproject.toml` under `web/api/`.

## Acceptance criteria

- [ ] `web/api/` contains a runnable FastAPI app; `uvicorn main:app --port 8090` starts cleanly.
- [ ] `alembic upgrade head` on a fresh DB creates `binding`, `issue`, `run`, `skill` tables with the columns above.
- [ ] Port binds `127.0.0.1` only (verified by `ss -tlnp | grep 8090` showing localhost).
- [ ] On startup with an empty DB, seed creates 2 bindings + ≥4 issues + ≥4 runs.
- [ ] `curl -s http://localhost:8090/api/health` returns `{"status":"ok"}`.
- [ ] `curl -s http://localhost:8090/api/bindings` returns JSON containing both `homelab` and `trading`.
- [ ] `curl -s http://localhost:8090/api/bindings/trading/issues` returns ≥2 issues, each carrying the projected `latest_verdict` / `latest_run_state`.
- [ ] `curl -s http://localhost:8090/api/issues/<id>` returns `comments_md` and `context_md` fields.
- [ ] `curl -s http://localhost:8090/api/issues/<id>/runs` returns ≥1 run row.
- [ ] `pyproject.toml` `[tool.pytest.ini_options] testpaths` includes `web/api/tests`.
- [ ] `web/README.md` documents dev loop (uvicorn invocation), SQLite path, DB-reset instructions.
- [ ] `web/api/tests/test_endpoints.py` exercises each endpoint with a temp DB fixture; all pass.

## Verification

```
cd /home/james/symphony && uv run pytest
```

## Blocked by

None — can start immediately.
