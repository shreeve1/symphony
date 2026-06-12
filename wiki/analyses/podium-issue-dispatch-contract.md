---
title: "Podium issue-field dispatch contract (model catalog, effort, skill, claude gate)"
type: analysis
status: promoted
created: 2026-06-12
updated: 2026-06-12
sources:
  - wiki/raw/sessions/2026-06-12-issue-dispatch-contract.md
  - model_catalog.py
  - scheduler.py
  - agent_runner.py
  - prompt_renderer.py
  - skill_mode_map.py
  - tests/test_dispatch_gate.py
confidence: high
tags: [podium, dispatch, models, skills, reasoning-effort, claude]
---

# Podium issue-field dispatch contract

Every operator-settable Issue field now has a real dispatch effect, enforced by a fail-loud gate. Before 2026-06-12, `preferred_model`, `reasoning_effort`, and `max_duration_seconds` were stored-but-dead, and `preferred_agent: claude` silently ran pi while the Run row claimed claude [source: wiki/raw/sessions/2026-06-12-issue-dispatch-contract.md#durable-facts].

## Dispatch gate

`scheduler._apply_dispatch_gate` runs after a candidate is reserved and before any state transition or context-compaction spend [source: scheduler.py]. It blocks the Issue (state `blocked` + comment) when:

- the resolved agent is not `pi` ("claude engine is not wired") — real adapter tracked in kanban `#040`;
- `preferred_model` is absent from `models.yml`, or the catalog itself fails validation;
- the resolved model entry belongs to a different agent (e.g. a claude model on a pi dispatch);
- `preferred_skill` has no skill-table row, or the row's `source` SKILL.md no longer exists on disk.

On success it annotates the candidate with `resolved_provider` and `resolved_model = "{id}:{reasoning_effort}"`; `_start_run_record` and the pi argv use these, so Run rows record what actually ran [source: scheduler.py; agent_runner.py]. Seven gate cases are covered in `tests/test_dispatch_gate.py`.

## Model catalog is the contract

`model_catalog.py` (shared by `web.api.main` `/options` and the scheduler) requires: unique ids, `agent` in `pi|claude`, `provider` on every pi entry, and exactly one `default: true` entry catalog-wide (currently `gpt-5.5`/`openai-codex`) [source: model_catalog.py; models.yml]. The default dispatches when `preferred_model` is unset; the new-issue modal preselects it [source: web/frontend/components/NewIssueModal.tsx]. `SYMPHONY_PI_MODEL`/`SYMPHONY_PI_PROVIDER` are a legacy Plane-path fallback only; the podium startup pi probe exercises the catalog default [source: main.py].

## Skill application

pi does not discover `~/.claude/skills`; the scheduler passes `--skill <SKILL.md parent dir>` resolved from the skill table `source` column, and `prompt_renderer` prepends "First, invoke the `{skill}` skill…" to the rendered prompt [source: agent_runner.py; prompt_renderer.py]. `mode_for_skill` normalizes slash-less catalog names so `dev-plan`/`dev-build` project plan/build mode again [source: skill_mode_map.py].

## Timeout

Global run timeout is 60 min (`config.py` default `3_600_000`, env `SYMPHONY_RUN_TIMEOUT_MS` override, both binding WORKFLOW.md frontmatters updated; frontmatter remains decorative for the actual subprocess kill). Per-issue `max_duration_seconds` was dropped — schema, API, UI, and migration `0006_drop_max_duration_seconds` [source: web/api/migrations/versions/0006_drop_max_duration_seconds.py].

## Live verification

Smoke issue 20 / run 13 (homelab): run row `pi / openai-codex / gpt-5.5:low / skill_invoked=question`, exit 0, verdict `done` in 67s; summary echoed the new 3600000 timeout [source: wiki/raw/sessions/2026-06-12-issue-dispatch-contract.md#evidence]. The post-run transition initially failed on live-DB drift — `alembic_version` was stamped `0005` but `inbox_dismissed_at` never existed; fixed with the 0005 DDL manually plus a pragma diff parity check [source: wiki/raw/sessions/2026-06-12-issue-dispatch-contract.md#durable-facts]. Root cause (confirmed post-session): `web/api/main.py` `ensure_schema` UPDATEd `alembic_version` to the code's `INITIAL_REVISION` on every boot, recording migrations that never ran. Fixed in commit `772e7ba`: existing databases are never re-stamped; startup runs a pragma drift check — missing columns raise before the API serves, extra columns (pending drop migration) warn [source: web/api/main.py; web/api/tests/test_ensure_schema.py].

## Supersedes

- [analyses/podium-014-new-issue-flow.md](podium-014-new-issue-flow.md) — "preferred_model free text, unlisted models still dispatch" no longer true.
- [analyses/podium-028-model-catalog-searchable-dropdowns.md](podium-028-model-catalog-searchable-dropdowns.md) — catalog promoted from dropdown aid to dispatch contract.
- [concepts/prompt-renderer.md](../concepts/prompt-renderer.md) — renderer now prepends the skill directive; timeout default 3600000.
- [concepts/thin-engine-v2.md](../concepts/thin-engine-v2.md) — provider/model no longer fixed per-host by env for Podium bindings.
- [sources/symphony-host-service-unit.md](../sources/symphony-host-service-unit.md) — `SYMPHONY_PI_*` env demoted to legacy fallback.
