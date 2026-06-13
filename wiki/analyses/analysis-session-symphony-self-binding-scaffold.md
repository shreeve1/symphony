---
title: symphony-binding-scaffold accuracy review, comment-stripping side effect, live self-binding
type: analysis
status: promoted
created: 2026-06-13
updated: 2026-06-13
sources:
  - .claude/skills/symphony-binding-scaffold/SKILL.md
  - skill_migration.py
  - web/api/db.py
  - scheduler.py
  - bindings.yml
  - wiki/raw/sessions/2026-06-13-symphony-self-binding-scaffold.md
confidence: high
tags: [scaffold, skill, binding, podium, bindings-yml, yaml, comment-stripping, self-binding, is_coding, operations]
---

# symphony-binding-scaffold: accuracy review → hardening → live self-binding

Session reviewed the `symphony-binding-scaffold` skill for accuracy, hardened the doc, then ran it to create a live `symphony` self-binding. Three durable outcomes plus one superseded claim.

## 1. Skill was functionally correct but instructionally thin

All referenced symbols exist and `tests/skills/test_binding_scaffold.py` passes. But the SKILL.md under-specified the actual call:

- Step "Run `scaffold_podium_binding(...)`" never named `PodiumBindingScaffoldRequest`, nor the required keyword-only `db_path` / `bindings_path` (`skill_migration.py:53-58`).
- No run command or cwd (module is repo-root; must run from `/home/james/symphony` via `uv run python`).
- Allowed enum values unstated: `default_agent ∈ {pi, claude}`, `binding_type ∈ {infra, coding}` (`skill_migration.py:67-70`).
- "Verification" only ran the tmp-fixture pytest — it did **not** verify the operator's new binding landed in the live DB/`bindings.yml`.
- No note that the written entry carries `plane_project_id` (transitional config-compat, `skill_migration.py:79`) or that the binding is not live until restart.

Fix: SKILL.md now carries the exact request-dataclass snippet, enums, db/bindings path resolution, a real DB-query + yaml-grep verification block, and the transitional-field + restart notes. The Plane-coupling guard test still passes.

## 2. Verified side effect: scaffold strips bindings.yml comments

`_append_binding` (`skill_migration.py:201-215`) reads with `yaml.safe_load`, mutates the dict, writes with `yaml.safe_dump`. PyYAML does not preserve comments across a load→dump round-trip, so the whole file is rewritten without any `#` lines. The live run deleted **77 lines** — the `# Plane rollback tracker_contract:` reference blocks under `homelab` and `trading` — and reflowed list indentation (`  - name:` → `- name:`).

Impact assessment: **no functional change**. `config.py` reads parsed YAML data (same as `safe_load`), so the scheduler behaves identically; only human-only annotation was lost, and it remains in git (`git show HEAD:bindings.yml`). James chose to leave the comments removed (dead Plane rollback data). The skill's "show the `bindings.yml` diff before committing" rule is the only current guard against silent comment loss — a `ruamel.yaml` swap or an explicit warning would harden `_append_binding`.

## 3. Live symphony self-binding created

Ran the scaffold against the live `podium.db` (resolved via `resolve_db_path()` → `/home/james/symphony/podium.db`; no `PODIUM_DB_PATH` on the unit, `/var/lib/symphony` absent). Created binding `symphony` (`type=coding`, `repo_path=/home/james/symphony`, `base_branch=main`, `default_agent=pi`, `tracker=podium`, `plane_project_id=symphony`). DB row + `binding_settings(threshold=16000)` inserted; `bindings.yml` appended as the 3rd entry. See [binding-symphony](../entities/binding-symphony.md). Highest-risk binding (self-binding; agents can edit scheduler source). Not live until restart; no real `WORKFLOW.md` yet.

## 4. C-0066 superseded — is_coding now per-binding

While assessing self-binding risk, verified `is_coding = tick_binding is not None and tick_binding.binding_type == "coding"` (`scheduler.py:948`). This keys off the per-tick binding, not `config.bindings[0].binding_type` as C-0066 described (old `scheduler.py:488`). The first-binding-wins bug is fixed, so the new `coding` `symphony` binding resolves correctly even though `homelab` (`infra`) is first in `bindings.yml`. C-0066 marked `superseded`.

## Follow-ups

- Restart `symphony-host.service` (ask James) to activate the binding.
- Author a real `WORKFLOW.md` for the symphony repo (`symphony-workflow-author`) before smoke/dispatch.
- Optionally harden `_append_binding` against comment loss.
