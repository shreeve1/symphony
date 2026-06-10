---
title: Podium #014 — new-issue flow, review hardening, and modal evolution
type: analysis
status: promoted
created: 2026-06-10
updated: 2026-06-10
sources:
  - wiki/raw/sessions/2026-06-10-podium-014-new-issue-flow.md
  - web/api/main.py
  - web/api/seed.py
  - web/api/tests/test_issue_create.py
  - web/frontend/components/NewIssueModal.tsx
  - web/README.md
confidence: high
tags: [podium, web-ui, fastapi, new-issue, optimistic-update, seeding, review]
---

# Podium #014 — new-issue flow, review hardening, and modal evolution

Kanban slice #014 closed the file → Todo front end of Podium's file → Todo → dispatch loop (dispatch itself is #020). Implementation landed in commit `a68cccf`, followed by four same-day commits driven by an independent review and operator UI preferences: `f0de67b` (all nine review findings), `4aab377` (flyout chip removal), `a6157f3` (modal flyout-parity), `bf7cfd0` (dropdowns + options endpoint). [source: wiki/raw/sessions/2026-06-10-podium-014-new-issue-flow.md#evidence]

## Endpoint contract

`POST /api/bindings/{name}/issues` returns 201 with the full row. Server-set: `state='todo'` (sending `state` → 400 via `extra="forbid"`). Server-defaulted but client-settable: `reasoning_effort` (`'high'`), `worktree_active` (`false`), `base_branch` (binding's `bindings.yml` entry). Unknown binding → 404, checked *before* body validation — precedence pinned by `test_create_unknown_binding_beats_body_validation`. Invalid values → 422. The 400/422 split reuses #013's hand-validation pattern (`Model.model_validate` + `extra_forbidden` scan). [source: web/api/main.py] [source: web/api/tests/test_issue_create.py]

`reasoning_effort` and `base_branch` were originally rejected as server-set (400) and only became settable in `a6157f3` when the modal grew flyout parity — an API loosening driven by UI needs. [source: wiki/raw/sessions/2026-06-10-podium-014-new-issue-flow.md#decisions]

## Seeding pivot

#014's acceptance criterion required `preferred_skill: "/diagnose"` → 201, but `issue.preferred_skill` is an FK to `skill(name)` under `PRAGMA foreign_keys = ON` and the seed catalog lacked `/diagnose`. Resolution: add `/diagnose` to `SEED_SKILLS` and replace insert-if-table-empty with per-row `INSERT OR IGNORE`, so databases seeded by earlier slices pick up new seed skills at next boot. Consequence for #015: boot seeding resurrects any seed row the catalog refresh deletes and never rewrites changed descriptions — #015 must retire `_seed_skills` or take table ownership (noted in its issue file). [source: web/api/seed.py] [source: wiki/raw/sessions/2026-06-10-podium-014-new-issue-flow.md#durable-facts]

## Options endpoint

`GET /api/bindings/{name}/options` (added `bf7cfd0`) feeds the modal dropdowns:

- `agents`: static `["pi", "claude"]`, mirroring the scheduler's `_validate_agent` set at `config.py:471`.
- `models`: `KNOWN_MODELS`, a curated placeholder — Symphony has no model catalog source of truth; the column stays free text server-side.
- `branches`: live `git for-each-ref refs/heads` against the binding's `repo_path` from `bindings.yml`; any failure (missing yml, no repo_path, not a git repo, timeout) degrades to `[]`, never a 500. [source: web/api/main.py]

## Modal UX

Submit prepends an optimistic temp card (negative id) to the `["issues", binding]` cache but the modal closes only on success; failure rolls the card back and keeps the modal open with an error line and typed values intact — a deliberate deviation from #014's "POST, close modal" spec wording, chosen when review flagged silent data loss. Submit disables while pending. TanStack Query v5 fires `useMutation`-level callbacks independent of component mount, so reconcile survives the close. Operator preferences applied the same day: flyout dropped the priority and max-duration chips (PATCH support retained; priority badge stays on cards), and the modal carries all flyout-editable fields as optional dropdowns/inputs with server-default placeholder text. [source: web/frontend/components/NewIssueModal.tsx] [source: wiki/raw/sessions/2026-06-10-podium-014-new-issue-flow.md#decisions]

## Operational notes

- Playwright specs write to the persistent dev DB by design (unique-title/idempotent-edit conventions); seed skills appear only after an API process restart since seeding runs in the FastAPI lifespan. Documented in `web/README.md`. [source: web/README.md]
- Watch item: editing.spec and new-issue.spec both exercise `/homelab` in parallel; one transient flake observed. Serialize or split bindings if it recurs. [source: wiki/raw/sessions/2026-06-10-podium-014-new-issue-flow.md#open-questions-and-follow-ups]
- Free-text `preferred_agent`/`preferred_model` reach dispatch unvalidated; #020 must fall back to binding defaults (noted in its issue file). [source: wiki/raw/sessions/2026-06-10-podium-014-new-issue-flow.md#durable-facts]
