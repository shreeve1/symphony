---
id: 028
title: Podium — models.yml catalog + agent-filtered searchable dropdowns
status: done
blocked_by: []
parent: null
priority: 0
created: 2026-06-12
updated: 2026-06-12
actor: ralph
---

## What to build

Replace the hardcoded `KNOWN_MODELS` placeholder (`web/api/main.py:396`,
"curated placeholder until a real catalog exists") with a git-tracked,
agent-tagged model catalog, and make the new-issue form's Skill / Model /
Agent / Branch dropdowns searchable. The Model dropdown filters to the
selected Agent's models.

Decision record: ADR-0006 context + `wiki/analyses/adr-0006-engine-state-polling.md`
(this slice is part of the UX/observability tuning plan). Catalog-store
decision: git-tracked YAML over a DB table, because models are *authored*
config (like `bindings.yml`), not *scanned/derived* data like the `skill`
table.

**1. `models.yml` at repo root.**

New file, auto-discovered at CWD like `bindings.yml`. Shape:

```yaml
models:
  - id: claude-opus-4-8
    agent: claude
    label: Opus 4.8
  - id: claude-fable-5
    agent: claude
  - id: claude-sonnet-4-6
    agent: claude
  - id: claude-haiku-4-5
    agent: claude
  - id: glm-5.1:high
    agent: pi
    provider: zai
```

Seed it from the current `KNOWN_MODELS` split by agent (the four `claude-*`
entries → `agent: claude`; `glm-5.1:high` → `agent: pi, provider: zai`).
`agent` must be one of `pi`, `claude` (mirror `config._validate_agent`).
`label` and `provider` are optional.

**2. `/options` reads the catalog.**

`GET /api/bindings/{name}/options` (`web/api/main.py:405`) stops returning
`KNOWN_MODELS`. It loads `models.yml` and returns models tagged by agent so
the frontend can filter — e.g.:

```json
{
  "agents": ["pi", "claude"],
  "models": [{"id": "claude-opus-4-8", "agent": "claude", "label": "Opus 4.8"}, ...],
  "branches": [...]
}
```

Loader degrades to `[]` on any failure (missing/invalid `models.yml`),
exactly like `_branches_for` (`web/api/main.py:420`). Delete the
`KNOWN_MODELS` constant (only referenced at `main.py:396,415` — clean
removal). `KNOWN_AGENTS` stays (it mirrors the validation set, not a
catalog). Add a `MODELS_PATH` + `_load_models()` loader mirroring the
`BINDINGS_PATH`/`_load_bindings` pattern (`web/api/main.py:48-49`), and
expose a small **shared validator** (`agent ∈ {pi,claude}`, `id` present,
no dup ids) that #032's `symphony-models` skill reuses — single source of
truth for catalog validity.

**This is a breaking change to the `/options` `models` shape** (string list
→ object list). The following must be updated in lockstep:
- `IssueOptions.models` in `web/frontend/lib/api.ts:120-124` changes from
  `string[]` to `{ id: string; agent: string; label?: string }[]`.
- `web/api/tests/test_issue_create.py:202-204`
  (`test_options_returns_agents_models_and_branches`) asserts
  `"claude-fable-5" in body["models"]` against a string list — rewrite to
  assert the object shape + agent tag. The `agents`/`branches` assertions
  and the 404 / branch-degradation tests stay.

**3. Searchable, agent-filtered comboboxes.**

Replace the native `<select>` `FieldSelect` in
`web/frontend/components/NewIssueModal.tsx` with a zero-dep searchable
combobox (text input + filtered dropdown list, matching current styling —
no new dependency; only `@radix-ui/react-slot` is present). Apply to Skill,
Model, Agent, Branch.

- Model combobox options = models whose `agent` equals the selected Agent;
  if no Agent is selected, show all models.
- Allow free-text entry for Model and Agent so unlisted values still work
  (C-0058: `preferred_agent`/`preferred_model` are free text end to end;
  dispatch falls back to binding defaults on unknown values). Skill stays
  selection-only (FK-validated).

## Acceptance criteria

- [x] `models.yml` exists at repo root, seeded with the five current models, agent-tagged; loads as valid YAML.
- [x] `GET /api/bindings/{name}/options` returns models from `models.yml` as `{id, agent, label?}` objects tagged by agent; `KNOWN_MODELS` constant removed.
- [x] `IssueOptions.models` TS type updated to the object shape; all consumers compile (`web/frontend/lib/api.ts`, `NewIssueModal.tsx`).
- [x] `web/api/tests/test_issue_create.py` options test updated to the new object shape (agents/branches/404/degradation assertions preserved).
- [x] Missing or invalid `models.yml` degrades `models` to `[]` without 500 (test asserts graceful fallback, mirroring the branches degradation test).
- [x] A shared `models.yml` validator (agent ∈ {pi,claude}, id present, no dup ids) exists and is unit-tested; reused by #032.
- [x] Backend test covers: catalog load, agent tags present, free-text model still accepted by `POST issues` (no FK on model).
- [x] Frontend dropdowns are searchable (type-to-filter) for Skill/Model/Agent/Branch.
- [x] Selecting Agent=`claude` shows only `claude-*` models; Agent=`pi` shows only pi models; no Agent shows all (Playwright assertion).
- [x] Model/Agent accept a typed free-text value not in the list (Playwright assertion); Skill does not.
- [x] `pnpm exec tsc --noEmit` passes.

## Implementation Notes

- Added repo-root `models.yml` seeded from the previous hardcoded model list with agent/provider/label metadata.
- Added shared backend catalog validation/loading and `/options` model-object responses with graceful missing/invalid catalog fallback.
- Updated the new-issue modal to use zero-dependency searchable comboboxes, with agent-filtered model choices and free-text Agent/Model support.
- Updated backend and Playwright coverage for model catalog loading, validator failures, free-text model creation, model filtering, and Skill selection-only behavior.

## Verification

```
cd /home/james/symphony && uv run pytest && \
cd web/frontend && pnpm exec tsc --noEmit && pnpm test:e2e
```

## Blocked by

- none
