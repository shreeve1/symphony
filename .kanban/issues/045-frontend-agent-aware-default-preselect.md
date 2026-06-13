---
id: 045
title: Agent-aware default model preselect in NewIssueModal
status: review
updated: 2026-06-13
actor: ralph
blocked_by: [041]
parent: null
priority: 2
created: 2026-06-13
---

## What to build

With #041, `models.yml` carries one `default: true` per agent, so `/api/bindings/{name}/options` returns two default-flagged models. `NewIssueModal.tsx` currently preselects the first `default: true` it finds (around line 250) regardless of the selected agent — with two defaults it can preselect a claude model while the agent control sits on pi, producing a fail-loud agent/model mismatch dispatch block on a form the operator never touched.

Make preselection agent-aware:

1. On mount and whenever the selected agent changes, preselect the model whose `default: true` AND whose `agent` matches the currently selected agent. If that agent has no default, fall back to the current placeholder/empty behavior (no silent cross-agent pick).
2. If the operator has manually chosen a model and then switches agent, the stale cross-agent model selection must be replaced by the new agent's default (or cleared if none) — never submit a known-mismatched pair from the default flow.
3. The existing agent-filtered model combobox behavior (#028) stays: the dropdown lists only models matching the selected agent, free-text override preserved.
4. Update/extend the Playwright spec (`web/frontend/tests/new-issue.spec.ts`, fixtures in `web/frontend/tests/fixtures.ts`) so the options fixture includes two defaults (one pi, one claude) and asserts: pi agent preselects the pi default; switching agent to claude re-preselects the claude default; switching back restores the pi default.

## Acceptance criteria

- [ ] With fixture defaults `gpt-5.5` (pi) and `claude-opus-4-8` (claude): modal opens with agent pi → model field shows `gpt-5.5`.
- [ ] Switching agent to claude → model field shows `claude-opus-4-8`; switching back to pi → `gpt-5.5`.
- [ ] Fixture variant where claude has no default: switching to claude leaves the model field empty/placeholder, not a pi model.
- [ ] Existing new-issue specs still pass.
- [ ] `cd web/frontend && npm run test:e2e -- new-issue.spec.ts` green.

## Verification

`cd /home/james/symphony/web/frontend && npm run test:e2e -- new-issue.spec.ts`

## Blocked by

- Blocked by #041
