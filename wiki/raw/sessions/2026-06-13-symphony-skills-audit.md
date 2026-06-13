# Session Capture: symphony-* skills audit and troubleshooter SQL fix

- Date: 2026-06-13
- Purpose: Review all 11 repo-local `symphony-*` skills for drift against current code after the #042–#046 / Podium churn, and fix any outdated content found.
- Scope: SKILL.md verification only — referenced functions, API endpoints, ports, test files, and SQLite column names checked against source. One fix applied.

## Durable Facts

- All 11 `symphony-*` skills were verified; 10 are clean against current code. — Evidence: `.claude/skills/symphony-*/SKILL.md`
- `symphony-troubleshooter` carried two stale SQLite fallback queries that reference columns the schema does not have. — Evidence: `.claude/skills/symphony-troubleshooter/SKILL.md`, `web/api/schema.py`
- The Podium `binding` table has only `name, display_name, color, sort_order, archived` — no `repo_path` or `default_agent`. Repo path and default agent live in `bindings.yml`, not Podium SQLite (Binding-is-Project). — Evidence: `web/api/schema.py:6`
- The Podium `run` table has `started_at` and `ended_at` (TIMESTAMP) and no `updated_at`; the `issue` table is the one with `updated_at`. — Evidence: `web/api/schema.py:54`, `web/api/schema.py:42`
- The pre-fix queries (`select name, repo_path, default_agent from binding`; `select ... updated_at from run order by updated_at`) would each fail with `no such column`. — Evidence: `web/api/schema.py`
- Skill references that verified clean: `scaffold_podium_binding` (`skill_migration.py:53`); `_load_models` (`web/api/main.py:552`) and `_validate_models` alias to `model_catalog.validate_models` (`web/api/main.py:549`); `resolve_db_path` (`web/api/db.py:13`); `web.cli.podium skills refresh` (`web/cli/podium.py:21-32`); API endpoints `GET /api/bindings`, `POST /api/bindings/{name}/issues`, `GET /api/issues/{issue_id}/runs`, `GET /api/runs/{run_id}`, `GET /api/bindings/{name}/options`, `GET /api/skills`, `GET /api/health` (`web/api/main.py:445-1357`); all 8 `tests/skills/` files. — Evidence: cited paths
- Podium API stays loopback (`127.0.0.1:8090`); only podium-web moved LAN-bound at #023d, so troubleshooter's API host is still correct. — Evidence: `wiki/sources/podium-systemd-units.md`
- consume-on-dispatch `preferred_skill` (ADR-0008, uncommitted at session time) is undocumented in any skill, but no skill needs it; `symphony-models` correctly states preferred_model/effort are standing config. — Evidence: `.claude/skills/symphony-models/SKILL.md`, `scheduler.py:1223`

## Decisions

- Apply the two SQL column fixes directly to `symphony-troubleshooter/SKILL.md` (binding → `name, display_name, archived`; run → `id, issue_id, state, verdict, summary, started_at, ended_at order by id desc`). James approved. — Evidence: this session
- Leave the other 10 skills unchanged. — Evidence: this session

## Evidence

- `web/api/schema.py:6,42,54` — authoritative binding/issue/run table columns.
- `.claude/skills/symphony-troubleshooter/SKILL.md` — the corrected DB fallback block.

## Exclusions

- No secret-env reads; no live service or DB mutation; no Plane calls. Review was read-only except the single skill-doc edit.

## Open Questions And Follow-Ups

- When ADR-0008 (`preferred_skill` consume-on-dispatch) is committed, consider whether any operator-facing skill should mention it.
