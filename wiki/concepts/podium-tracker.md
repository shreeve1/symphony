---
title: Podium Tracker — schema, db resolution, API contract, concurrency
type: concept
status: promoted
created: 2026-06-10
updated: 2026-06-24
sources:
  - web/api/schema.py
  - web/api/db.py
  - web/api/main.py
  - web/api/seed.py
  - web/api/migrations/versions/0001_initial.py
  - tracker_podium.py
  - tracker_adapter.py
  - config.py
  - main.py
  - scheduler.py
confidence: high
tags: [podium, sqlite, schema, run-table, issue-state, db-path, patch-contract, check-same-thread, alembic, lan-bind, tracker-adapter]
---

# Podium Tracker (implementation)

Live code grounding for the Symphony-native tracker built across slices #012a–#013. Design rationale in [analyses/adr-0005-replace-plane-with-podium.md](../analyses/adr-0005-replace-plane-with-podium.md). Endpoint/modal UX (#014) in [analyses/podium-014-new-issue-flow.md](../analyses/podium-014-new-issue-flow.md).

## Stack

FastAPI + raw `sqlite3` (no ORM) + Pydantic v2 for the API; Alembic migrations checked in (`web/api/migrations/versions/0001_initial.py`, revision `0001_initial`). Schema also mirrored as `SCHEMA_SQL` in `web/api/schema.py` for `CREATE TABLE IF NOT EXISTS` boot path. Next.js 15 / React 19 + TanStack Query v5 + Tailwind + Playwright on the frontend [source: web/api/schema.py, web/api/migrations/versions/0001_initial.py].

## Two distinct state enums (do not conflate)

- **`issue.state`**: `todo`, `in_review`, `running`, `blocked`, `done`, `archived` — board column / lifecycle [source: web/api/schema.py].
- **`run.state`**: `queued`, `running`, `succeeded`, `failed` — dispatch state machine [source: web/api/schema.py:51]. Also mirrored as `issue.latest_run_state` (nullable) [source: web/api/schema.py:40].
- **verdict** (`run.verdict`, `issue.latest_verdict`): `done`, `review`, `blocked`, nullable [source: web/api/schema.py:39,52].

The startup reaper (ADR-0005) sweeps `run.state IN (queued,running)` → synthetic `failed` + `restart-orphan` summary.

## Tables

- `binding(name PK, display_name, color, sort_order, archived)` — Binding *is* the Project; no Project table.
- `skill(name PK, description, source)` — CLI-refreshable catalog.
- `issue(...)` — operator intent + latest-Run projection. Typed operator levers: `preferred_agent`, `preferred_model`, `preferred_skill` (FK→skill.name), `reasoning_effort` DEFAULT `'high'`, `worktree_active` DEFAULT FALSE, `auto_land` BOOLEAN NOT NULL DEFAULT FALSE (slicer/review provenance), dependency fields `blocked_by` (list of issue ids, JSON text) and `locks` (list of lock labels, JSON text), infra role columns `approval_required` DEFAULT FALSE, `approved` DEFAULT FALSE, `scheduled_for` TIMESTAMP NULL, `base_branch`. Two blobs: `comments_md` (human↔AI), `context_md` (AI-only). Projection cols: `latest_run_id` (FK→run.id), `latest_verdict`, `latest_run_state`, `last_event_at`.
- `run(...)` — first-class per-dispatch row: `agent, provider, model, state, verdict, summary, exit_code, cost_usd, input_tokens, output_tokens, worktree_path, branch_name, base_branch, log_path, skill_invoked, started_at, ended_at`. No event-log table v1.
[source: web/api/schema.py:6-65]

FK note: only `preferred_skill` is FK-checked; `preferred_agent`/`preferred_model` are free text (no enum/FK) — see C-0058. `PRAGMA foreign_keys = ON` is set per-connection [source: web/api/db.py:39].

## Engine tracker adapter (#019)

`bindings.yml` accepts optional `tracker: plane|podium` on each binding. Missing value defaults to `plane`; unknown values raise `ConfigError` during config load [source: config.py:64-70,376-379]. `main._build_binding_runtime(...)` selects `PodiumTrackerAdapter` when `binding.tracker == "podium"`, otherwise builds the Plane transport/adapter path [source: main.py:76-81].

`tracker_adapter.py` defines the runtime-checkable `TrackerAdapter` Protocol used as the shared engine surface: candidate listing, state transitions, comment/context writes, label no-ops/updates, and run row get/record [source: tracker_adapter.py:13-49]. `tracker_podium.py` implements that surface against SQLite without importing `plane_adapter`; role projection is column-based: state Roles map to `issue.state`, mode Roles derive from `preferred_skill` via `skill_mode_map`, agent role is exposed as `agent:<preferred_agent>`, and infra approval/schedule Roles project through `approval_required`, `approved`, and due `scheduled_for` values [source: tracker_podium.py; wiki/analyses/podium-023c-homelab-cutover.md].

Podium tracker connections set `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000`, and `PRAGMA foreign_keys = ON`. FastAPI's `web/api/db.py` connect path now sets the same WAL/busy-timeout pragmas, so API and engine writers share the same SQLite concurrency posture [source: tracker_podium.py:95-102, web/api/db.py:37-41].

Scheduler success handling appends the concise completion summary to `comments_md` and, for adapters with `stores_context=True`, appends sanitized stdout/stderr blobs into `context_md` before moving the issue to `in_review` [source: scheduler.py:852-870, tracker_podium.py:69,209-215].

## DB path resolution chain

`resolve_db_path()`: `PODIUM_DB_PATH` env override → else `/var/lib/symphony/podium.db` if its parent exists and is writable → else repo-root `podium.db` fallback. Run logs root: `/var/lib/symphony/runs` [source: web/api/db.py:8-22].

## check_same_thread=False (deliberate)

`connect()` opens sqlite with `check_same_thread=False` because FastAPI runs the sync `get_connection` dependency and the sync endpoint in **different anyio threadpool threads** — a per-request connection is legitimately created in one thread and used in another. Never shared *concurrently* (one request: sequential yield→endpoint→close), so disabling the guard is safe. This was a #012b review finding with regression test `test_concurrent_reads_do_not_cross_threads` [source: web/api/db.py:32-40].

## PATCH contract (origin of the 400/422 split)

`PATCH /api/issues/{id}`: hand-validation via `IssuePatch.model_validate(body)`. `extra="forbid"` → unknown field raises `extra_forbidden` → **400**; any other validation error → **422** [source: web/api/main.py:326-330]. Then:

- **null guard**: `NON_NULLABLE_FIELDS` set to null in the body → 422 "fields cannot be null" [source: web/api/main.py:333-337].
- **skill FK check**: non-null `preferred_skill` → `_require_known_skill` [source: web/api/main.py:339-340].
- **no-op guard**: only fields whose value differs from stored are `changed`; empty/echoing body returns `current` unchanged and does **not** bump `updated_at` — the board orders by `updated_at`, so a blind bump would reorder cards [source: web/api/main.py:342-346].
- **monotonic updated_at**: `_next_updated_at` returns a value strictly greater than the stored one even when two PATCHes land within clock resolution [source: web/api/main.py].
- **dependency fields**: `blocked_by` and `locks` are accepted on create and patch. API rows return omitted/malformed stored values as `[]`; writes store JSON text. `blocked_by` is cycle-checked and a dependency cycle returns HTTP 400; `locks` are labels and have no cycle check (C-0317) [source: web/api/main.py; web/api/tests/test_issue_create.py; web/api/tests/test_issue_patch.py].
- **auto-land provenance**: `issue.auto_land` landed in Alembic `0011_issue_auto_land` and `SCHEMA_SQL` as `BOOLEAN NOT NULL DEFAULT FALSE`; `PodiumTrackerAdapter._row_to_issue` exposes it as a Python bool defaulting `False` (C-0320) [source: web/api/schema.py; web/api/migrations/versions/0011_issue_auto_land.py; tracker_podium.py; tests/test_tracker_podium.py].

POST `/api/bindings/{name}/issues` uses the same `model_validate` 400/422 split; unknown binding → 404 checked **before** body validation (C-0054). Board list orders `BY updated_at DESC, id DESC` [source: web/api/main.py].

## LAN-bind deviation

Both Podium ports bind localhost in production; external access via Authelia reverse proxy on 9091 (not CORS — proxy fronts the loopback backend). Auth deferred to #018; `PODIUM_PASSWORD_HASH` (bcrypt, single shared password) is the planned mechanism per ADR-0005.

## Seeding

`seed.py` `_seed_skills` = per-row `INSERT OR IGNORE` over `SEED_SKILLS` (incl. `/diagnose`) at every boot (FastAPI lifespan). Resurrects deleted seed rows, never rewrites descriptions — #015 must retire `_seed_skills` or own the `skill` table (C-0055). Binding/issue seed (`seed_if_empty`) is insert-if-`binding`-table-empty, reads `bindings.yml` [source: web/api/seed.py:19-99].

## Judgment calls (deferred / deviations)

- `reasoning_effort` enum invented at API layer (no upstream catalog); `KNOWN_MODELS` is a hand-curated placeholder, no real model catalog source exists (C-0056).
- Last-write-wins concurrency: multi-writer reconciliation deferred to #017; monotonic `updated_at` is the v1 mitigation.
- `cost_usd` captured in the `run` row but deliberately hidden from the operator board surface.
- Resizable flyout was an operator-requested UI deviation from the #013 spec.

## Slice → commit map

`ca1b8b7` #012a (schema/endpoints), `6ca9ec1` #012b (review hardening), `276228d` cross-thread fix, `9d930b1` #012c, `ef79c7a` #013 (flyout), `2f28152` #013 review, `a68cccf` #014, `f0de67b` #014 review, `4aab377` flyout chip removal, `a6157f3` modal flyout-parity, `bf7cfd0` options endpoint, `9e84869`/`37c5170` #019 Podium tracker adapter. `.kanban/` is gitignored — cite code paths + commits primarily, kanban paths secondarily.

## Claims

C-0059 .. C-0067, C-0079 .. C-0081, C-0104 .. C-0106, C-0317, and C-0320 in [CLAIMS.md](../CLAIMS.md).
