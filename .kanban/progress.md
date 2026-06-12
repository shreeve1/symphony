# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.


## #028 Podium — models.yml catalog + searchable dropdowns — 2026-06-12

**What changed:** Added repo-root `models.yml`, backend model catalog validator/loader, `/options` model-object response shape, typed frontend `ModelOption`, searchable new-issue comboboxes, agent-filtered model choices, and regression/e2e coverage.
**Files:** `models.yml`, `web/api/main.py`, `web/api/tests/test_issue_create.py`, `web/frontend/lib/api.ts`, `web/frontend/components/NewIssueModal.tsx`, `web/frontend/tests/new-issue.spec.ts`.
**Decisions:** Model catalog is git-tracked YAML authored config; `preferred_model` and `preferred_agent` stay free-text end to end, while Skill remains selection-only because backend FK validation still applies.
**Conventions established:** `/api/bindings/{name}/options` returns `models` as `{id, agent, label?, provider?}` objects loaded through `_validate_models`; missing or invalid `models.yml` degrades to an empty model list without failing the endpoint.
**Notes for next iteration:** #032 should reuse `_validate_models()` for the `symphony-models` skill instead of reimplementing catalog validation.
