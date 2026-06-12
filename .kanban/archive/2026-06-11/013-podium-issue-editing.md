---
id: 013
title: Podium issue editing — typed columns + Comments/Context writes
status: done
blocked_by: [012c]
parent: null
priority: 0
created: 2026-06-10
---

## What to build

Turn the read-only prototype into a CRUD app. Every operator-settable field
on `issue` becomes editable via PATCH; the flyout grows inline editors for
the typed columns and markdown textareas for `comments_md` and `context_md`.

Endpoints to add:

- `PATCH /api/issues/{id}` — accepts any subset of editable fields:
  `title, description, state, priority, preferred_agent, preferred_model,
  preferred_skill, reasoning_effort, worktree_active, max_duration_seconds,
  base_branch, comments_md, context_md`. Returns the updated row.
- Body validation: enums constrained, unknown fields rejected with 400.
- `updated_at` bumped server-side.

Frontend:

- Flyout fields become editable in place. Each chip opens an inline picker
  (select/segmented control). Text fields commit on blur with debounce.
- `comments_md` and `context_md` get a side-by-side preview-on-toggle
  markdown editor (no live render; just textarea + "Preview" button).
- Optimistic updates via TanStack Query mutations; rollback on 4xx.

Out of scope: WebSocket sync (S017), auth (S018), new-issue creation (S014).

## Acceptance criteria

- [x] `PATCH /api/issues/{id}` with each editable field round-trips through SQLite (covered by `web/api/tests/test_issue_patch.py` — one test per field, both happy-path and validation failure).
- [x] Unknown field in PATCH body returns 400 with a Pydantic error.
- [x] Enum field with invalid value returns 422.
- [x] `updated_at` increases monotonically on every PATCH (test asserts).
- [x] Playwright `editing.spec.ts` flow: open flyout → change `state` chip → close flyout → reload page → state persisted. Repeated for `priority`, `preferred_skill`, `worktree_active` toggle, and `comments_md` edit.
- [x] Optimistic update reverts visibly when API returns 4xx (test stubs a failure and asserts the chip reverts).

## Verification

```
cd /home/james/symphony && uv run pytest && \
cd web/frontend && pnpm test:e2e
```

## Blocked by

- #012 (Phase 1 prototype must exist before editing can layer on it)

## Implementation record (2026-06-10)

Landed in two commits on `main`:

- `ef79c7a` — PATCH endpoint + inline flyout editors. Backend validates by
  hand to split unknown-field 400 from invalid-value 422; `updated_at` bump is
  strictly monotonic server-side; `preferred_skill` validated against the
  `skill` table, with `seed.py` seeding a placeholder catalog (`tdd`,
  `code-review`, `blueprint`) until #015. Frontend: nine editable chips,
  blur-commit text/number chips, textarea + preview-on-toggle editors for
  `comments_md`/`context_md`, optimistic mutations with rollback.
- `2f28152` — independent review follow-up (Opus reviewer, 0 Critical /
  2 Warning / 10 Note): no-op PATCH guard (empty or echoing body no longer
  bumps `updated_at` / reorders the board), new `GET /api/skills` feeding a
  `preferred_skill` select instead of free text, digits-only `ChipNumber`
  parsing.

Judgment calls / deviations from spec:

- `reasoning_effort` enum set to `minimal|low|medium|high` — no canonical list
  exists in scheduler source; nothing downstream reads it yet.
- `title`/`description` editable via API but have no UI editors (frontend
  scope read as typed columns + two markdown blobs).
- Text chips commit on plain blur; no debounce layer (single commit event).
- Review carry-over: no optimistic-concurrency control (last-write-wins);
  recorded on #017 where two live tabs make it reachable.

Verification: 460 pytest, tsc clean, 7/7 Playwright (run twice to prove
idempotency against the persistent dev db).
