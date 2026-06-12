---
title: "Podium #028 — models.yml catalog and searchable dropdowns"
type: analysis
status: promoted
created: 2026-06-12
updated: 2026-06-12
sources:
  - models.yml
  - web/api/main.py
  - web/api/tests/test_issue_create.py
  - web/frontend/lib/api.ts
  - web/frontend/components/NewIssueModal.tsx
  - web/frontend/tests/new-issue.spec.ts
  - .kanban/progress.md
confidence: high
tags: [podium, web-ui, model-catalog, options, combobox, ralph]
---

# Podium #028 — models.yml catalog and searchable dropdowns

#028 landed the first non-ADR piece of the ADR-0006 UX/observability tuning plan: model choices now come from authored repo config instead of a hardcoded placeholder, and the new-issue modal uses searchable comboboxes for high-cardinality fields. [source: .kanban/progress.md]

## Model catalog contract

`models.yml` at the repo root is the source of truth for UI model choices. It is auto-discovered relative to the repo root like `bindings.yml`, and the initial catalog is seeded from the former hardcoded list: four `claude-*` entries tagged `agent: claude` and one `glm-5.1:high` tagged `agent: pi` with `provider: zai`. Optional `label` and `provider` fields are preserved in the API response. [source: models.yml]

`web/api/main.py` now defines `MODELS_PATH`, `_load_models()`, and `_validate_models()`. The validator is the shared catalog gate future tooling should reuse: the top-level document must contain a `models` list, each entry must have a non-empty `id`, `agent` must be one of `pi` or `claude`, and duplicate ids are rejected. [source: web/api/main.py] [source: web/api/tests/test_issue_create.py]

`GET /api/bindings/{name}/options` returns `models` as objects (`{id, agent, label?, provider?}`) instead of strings. Missing, unreadable, malformed, or schema-invalid `models.yml` degrades to `models: []` without turning the endpoint into a 500, mirroring branch-list degradation. `KNOWN_MODELS` was removed; `KNOWN_AGENTS` stays because it mirrors scheduler validation rather than an authored catalog. [source: web/api/main.py] [source: web/api/tests/test_issue_create.py]

## Frontend contract

`IssueOptions.models` is now `ModelOption[]`, and `NewIssueModal` filters model options by the selected Agent. With no Agent selected, all catalog models are shown; with `claude`, only `claude-*` models are shown; with `pi`, only pi models are shown. [source: web/frontend/lib/api.ts] [source: web/frontend/components/NewIssueModal.tsx]

The native `FieldSelect` was replaced with a zero-dependency `FieldCombobox` for Skill, Effort, Agent, Model, and Base branch. Agent, Model, and Base branch run in free-text mode; Skill remains selection-only because `preferred_skill` is FK-validated server-side. `preferred_agent` and `preferred_model` remain free text end to end, so unlisted models still dispatch and server-side validation does not reject them. [source: web/frontend/components/NewIssueModal.tsx] [source: web/api/main.py]

## Verification

Backend tests cover object-shaped `/options` models, catalog validation failures, invalid/missing catalog fallback, and free-text model creation. Playwright covers combobox search/filter behavior, agent-filtered models, free-text Agent/Model persistence, and Skill selection-only reset. Full Ralph verification passed with `uv run pytest`, `pnpm exec tsc --noEmit`, `pnpm test:e2e`, and touched-file LSP diagnostics clean. The fresh review returned `RALPH_REVIEW: PASS_WITH_NOTES` because one reviewer run observed an unrelated `live-sync.spec.ts` flake; the implementer full verification run had all 16 e2e tests passing. [source: web/api/tests/test_issue_create.py] [source: web/frontend/tests/new-issue.spec.ts] [source: .kanban/progress.md]

## Follow-up

#032 `symphony-models` should call or otherwise reuse `_validate_models()` rather than duplicating validation rules. [source: .kanban/progress.md]

## Claims

C-0114, C-0115 in [CLAIMS.md](../CLAIMS.md). C-0114 supersedes C-0056's older `KNOWN_MODELS` placeholder wording.
