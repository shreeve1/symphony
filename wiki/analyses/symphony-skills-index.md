---
title: Symphony skills index
type: analysis
status: promoted
created: 2026-06-09
updated: 2026-06-16
sources:
  - .claude/skills/symphony-binding-scaffold/SKILL.md
  - .claude/skills/symphony-binding-remove/SKILL.md
  - .claude/skills/symphony-offboard-project/SKILL.md
  - .claude/skills/symphony-binding-smoke/SKILL.md
  - .claude/skills/symphony-bindings-status/SKILL.md
  - .claude/skills/symphony-onboard-project/SKILL.md
  - .claude/skills/symphony-plane-recover/SKILL.md
  - .claude/skills/symphony-project-scaffold/SKILL.md
  - .claude/skills/symphony-restart/SKILL.md
  - .claude/skills/symphony-troubleshooter/SKILL.md
  - .claude/skills/symphony-workflow-author/SKILL.md
  - .claude/skills/symphony-skills/SKILL.md
  - .claude/skills/symphony-models/SKILL.md
  - skill_migration.py
  - tests/skills/
  - tests/skills/test_restart_troubleshooter.py
  - tests/skills/test_binding_remove.py
  - tests/skills/test_offboard_project.py
confidence: high
tags: [skills, claude-code, onboarding, operations, scaffold, smoke, recovery, podium]
---

# Symphony skills index

Symphony now carries repo-local Podium-era `symphony-*` skill docs under `.claude/skills/` for the migrated operational suite. #027 made the Podium migration reviewable and testable inside this repository [source: .claude/skills/symphony-binding-scaffold/SKILL.md] [source: tests/skills/test_binding_scaffold.py]. #032 extends the suite with manual catalog-maintenance skills for the Skill table and `models.yml` dropdown catalog [source: .claude/skills/symphony-skills/SKILL.md] [source: .claude/skills/symphony-models/SKILL.md] [source: tests/skills/test_catalog_maintenance_skills.py]. The remaining operational skills, `symphony-restart` and `symphony-troubleshooter`, are now repo-local and Podium-aware instead of living only in the dotfiles/global skill tree; the stale global `symphony-*` copies were removed in dotfiles commit `06fa9a6` so project-local skills load without collisions [source: .claude/skills/symphony-restart/SKILL.md] [source: .claude/skills/symphony-troubleshooter/SKILL.md] [source: tests/skills/test_restart_troubleshooter.py].

## Lifecycle map

```text
new Podium binding flow:
  symphony-binding-scaffold → symphony-workflow-author → symphony-restart → symphony-binding-smoke
  └── orchestrated by: symphony-onboard-project

binding teardown (inverse of onboard):
  symphony-bindings-status → symphony-binding-remove → cleanup leftover references/tests → symphony-restart
  ├── archive (default, reversible) | purge (destructive)
  └── orchestrated by: symphony-offboard-project

legacy Plane retirement:
  symphony-plane-recover

operations / situational awareness:
  symphony-bindings-status
  symphony-restart
  symphony-troubleshooter

manual catalog maintenance:
  symphony-skills → refresh Podium skill table from .claude/skills
  symphony-models → edit/lint models.yml with shared validator
```

## Podium migration summary (#027)

- `symphony-binding-scaffold` is the new Podium binding creation path. It creates a Podium `binding` row and appends a `tracker: podium` entry to `bindings.yml`; no Plane API or `plane_adapter` path participates [source: .claude/skills/symphony-binding-scaffold/SKILL.md] [source: skill_migration.py].
- `symphony-binding-smoke` creates a smoke Issue via `POST /api/bindings/{name}/issues` and polls `GET /api/issues/{issue_id}/runs`, replacing the former Plane issue/comment polling path [source: .claude/skills/symphony-binding-smoke/SKILL.md] [source: skill_migration.py].
- `symphony-bindings-status` reads `GET /api/bindings` plus per-binding `GET /api/bindings/{name}/issues`; Plane project reads are no longer part of the migrated status path [source: .claude/skills/symphony-bindings-status/SKILL.md] [source: skill_migration.py].
- `symphony-project-scaffold` is now documented as a deprecated Plane-only alias for rollback/legacy hedge; new onboarding must use `symphony-binding-scaffold` [source: .claude/skills/symphony-project-scaffold/SKILL.md].
- `symphony-plane-recover` is explicitly a Plane retirement tool, not a new-project onboarding path [source: .claude/skills/symphony-plane-recover/SKILL.md].
- `symphony-workflow-author` is tracker-agnostic because it edits repository `WORKFLOW.md` policy on disk and render-tests against `prompt_renderer.py`; it does not write Podium or Plane [source: .claude/skills/symphony-workflow-author/SKILL.md].
- `symphony-onboard-project` now calls `symphony-binding-scaffold → symphony-workflow-author → symphony-restart → symphony-binding-smoke`, and explicitly does not call `symphony-project-scaffold` or `symphony-plane-recover` for normal Podium onboarding [source: .claude/skills/symphony-onboard-project/SKILL.md].

## Per-skill summary

### `symphony-skills`

Refreshes the Podium `skill` table from repo-local `.claude/skills/**/SKILL.md` files by wrapping `python -m web.cli.podium skills refresh`: dry-run first, operator confirmation, then live refresh. The skill explicitly forbids service restarts, Plane calls, env-file reads, and secret printing [source: .claude/skills/symphony-skills/SKILL.md] [source: tests/skills/test_catalog_maintenance_skills.py].

### `symphony-models`

Maintains repo-root `models.yml` as authored git-tracked config. It documents list/add/remove edits and lints via `web.api.main._load_models()` / `_validate_models()` so it reuses the #028 catalog contract (`agent` in `pi|claude`, `provider` required for pi entries, uniqueness by `(agent, provider, id)`, optional `label`) instead of adding bespoke helper code. The skill reminds operators that `preferred_model` is the dispatch contract, keeps one `default: true` per dispatchable agent, and forbids service restarts, Plane calls, env-file reads, direct DB edits, and secret printing [source: .claude/skills/symphony-models/SKILL.md] [source: model_catalog.py] [source: tests/skills/test_catalog_maintenance_skills.py].

### `symphony-binding-scaffold`

Creates a Podium-backed binding by inserting the binding row in Podium SQLite and appending `tracker: podium` to `bindings.yml`. The helper function `scaffold_podium_binding(...)` writes both sides and keeps `plane_project_id` only as transitional `ProjectBinding` compatibility while config still requires that field [source: skill_migration.py] [source: tests/skills/test_binding_scaffold.py].

### `symphony-binding-remove`

Inverse of `symphony-binding-scaffold`. Removes a binding by dropping its `bindings.yml` entry and either archiving (default, reversible — sets `binding.archived = TRUE`, preserves Issue/Run history) or purging (destructive — deletes the binding's Runs, Issues, `binding_settings`, and `binding` row). The helper `remove_podium_binding(...)` raises if the name is absent from both `bindings.yml` and the Podium DB; if present in only one, it removes what it finds and reports the other as `absent`. No Plane API or `plane_adapter` path participates. The removed binding stays live in memory until `symphony-host.service` reloads `bindings.yml` via `symphony-restart` [source: skill_migration.py] [source: tests/skills/test_binding_remove.py]. The purge path issues `PRAGMA defer_foreign_keys = ON` to resolve the `issue.latest_run_id` ↔ `run.issue_id` FK cycle that otherwise fails under `foreign_keys = ON` (C-0208); `binding_settings` is removed by its `ON DELETE CASCADE`. SKILL.md additionally documents the `bindings.yml` comment-stripping yaml round-trip (shared with scaffold, C-0171), a self-binding caveat for the `symphony` binding, how to reverse an archive, and the required post-removal cleanup pass for seed-dependent tests/code references. That cleanup exists because test DB seeding follows live `bindings.yml`, so hardcoded references to a removed binding produce 404s or empty lists after teardown; seed-dependent tests should be retargeted to a surviving same-type binding, while self-contained tmp-DB or `_bindings_override` tests can keep the old name [source: .claude/skills/symphony-binding-remove/SKILL.md] [source: web/api/seed.py] [source: web/api/tests/test_endpoints.py] [source: tests/skills/test_binding_smoke.py] [source: tests/skills/test_bindings_status.py].

### `symphony-binding-smoke`

Files one low-risk smoke Issue through Podium and polls Run rows. Verification is local Podium API state; it must not emit live alert/paging notifications during tests [source: .claude/skills/symphony-binding-smoke/SKILL.md] [source: tests/skills/test_binding_smoke.py].

### `symphony-bindings-status`

Read-only status from Podium bindings and issues. The helper `podium_bindings_status(...)` returns per-binding open Issue counts and latest Issue/Run state [source: skill_migration.py] [source: tests/skills/test_bindings_status.py].

### `symphony-project-scaffold`

Deprecated Plane-only scaffold alias retained for rollback or a deliberate legacy path. It is no longer the normal new-binding path [source: .claude/skills/symphony-project-scaffold/SKILL.md].

### `symphony-plane-recover`

Legacy Plane retirement/recovery only. Use it for archive/state-fill during Plane shutdown, not for Podium onboarding [source: .claude/skills/symphony-plane-recover/SKILL.md].

### `symphony-workflow-author`

Tracker-agnostic Workflow authoring. It writes repo policy on disk and avoids tracker writes entirely, so both Podium and legacy Plane can render the resulting `WORKFLOW.md` [source: .claude/skills/symphony-workflow-author/SKILL.md].

### `symphony-onboard-project`

Umbrella for Podium onboarding. It composes binding scaffold, workflow authoring, restart, and binding smoke while preserving sub-skill gates [source: .claude/skills/symphony-onboard-project/SKILL.md].

### `symphony-offboard-project`

Umbrella for Podium binding teardown, the inverse of `symphony-onboard-project`. It chains `symphony-bindings-status` → `symphony-binding-remove` → cleanup leftover references/tests → `symphony-restart` with a checkpoint between each step, owns no direct mutations, defaults to archive (purge stays gated behind the `symphony-binding-remove` confirmation), and does not call `symphony-plane-recover` (legacy Plane retirement, not Podium teardown) [source: .claude/skills/symphony-offboard-project/SKILL.md] [source: tests/skills/test_offboard_project.py]. The cleanup checkpoint mirrors `symphony-binding-remove` step 5: scan for removed-binding references, retarget seed-dependent tests to a live same-type binding, leave self-contained tmp/override tests alone, and run `uv run pytest` before restart [source: .claude/skills/symphony-offboard-project/SKILL.md].

### `symphony-restart` and `symphony-troubleshooter`

These operational skills are now tracked in the repo. `symphony-restart` remains the gated `symphony-host.service` restart ritual: pre-sanity, explicit James approval, restart, then `symphony_started` / reconcile / dispatch log verification. `symphony-troubleshooter` is read-only and Podium-era: it correlates `symphony-host.service`, Podium services, `/api/bindings` reads, SQLite Issue/Run rows, journal lifecycle lines, and hands mutations to the proper skill [source: .claude/skills/symphony-restart/SKILL.md] [source: .claude/skills/symphony-troubleshooter/SKILL.md] [source: tests/skills/test_restart_troubleshooter.py]. On 2026-06-13 a full audit of all 11 `symphony-*` skills found only `symphony-troubleshooter` stale: its DB fallback queried `binding.repo_path`/`binding.default_agent` (columns that live in `bindings.yml`, not the `binding` table) and `run.updated_at` (the `run` table has `started_at`/`ended_at`); both were corrected to match `web/api/schema.py`, the other 10 skills verified clean (C-0168) [source: .claude/skills/symphony-troubleshooter/SKILL.md] [source: web/api/schema.py] [source: wiki/raw/sessions/2026-06-13-symphony-skills-audit.md].

## Safety pattern after Podium migration

Migrated skills avoid Plane API endpoints and `plane_adapter` imports. Tests under `tests/skills/` assert the Podium endpoint strings and no legacy workspace endpoint coupling for migrated docs, while `skill_migration.py` provides testable helper seams [source: tests/skills/test_binding_scaffold.py] [source: tests/skills/test_binding_smoke.py] [source: tests/skills/test_bindings_status.py]. Catalog-maintenance skill tests also assert no Plane workspace strings, no service restart posture, and reuse of the shared model validator for `models.yml` edits [source: tests/skills/test_catalog_maintenance_skills.py]. Operational-skill tests assert `symphony-restart` keeps the approval gate and `symphony-troubleshooter` uses Podium-era read-only paths without stale Plane scaffold language [source: tests/skills/test_restart_troubleshooter.py].

## Related

- [Podium tracker](../concepts/podium-tracker.md) — Podium schema and tracker adapter.
- [ADR-0005 replace Plane with Podium](adr-0005-replace-plane-with-podium.md) — retirement decision and Binding-is-Project model.
- [Symphony operations](../concepts/symphony-operations.md) — restart ritual, alerts, and service context.
