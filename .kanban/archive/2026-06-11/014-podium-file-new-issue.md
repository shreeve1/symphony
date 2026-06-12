---
id: 014
title: Podium — file a new issue (title, description, preferred_skill)
status: done
blocked_by: [012c]
parent: null
priority: 0
created: 2026-06-10
---

## What to build

Operator-facing "New Issue" flow. Closes the file → Todo → dispatch loop's
front end (dispatch itself lands later in S020).

Endpoint:

- `POST /api/bindings/{name}/issues`
  - Body: `{title, description, priority?, preferred_skill?, preferred_agent?,
    preferred_model?, worktree_active?}`.
  - Server-side defaults: `state = 'todo'`, `reasoning_effort = 'high'`,
    `worktree_active = false`, `base_branch` from `bindings.yml`.
  - Returns 201 with the new row.

Frontend:

- "+ New Issue" button in the binding header (sidebar context) opens a modal.
- Required fields: title. Optional: description, priority, preferred_skill.
- `preferred_skill` dropdown reads from the static fake-seeded `skill` table
  (S015 replaces with real catalog refresh).
- On submit: POST, close modal, optimistically prepend the new card to the
  Todo column. Server returns the canonical row; reconcile.

Out of scope: skill catalog auto-refresh (S015), the dispatch trigger (S020).

## Acceptance criteria

- [ ] `POST /api/bindings/trading/issues` with `{"title": "smoke", "preferred_skill": "/diagnose"}` returns 201 with `state='todo'`, server-assigned `id`, defaults populated.
- [ ] Missing `title` returns 422.
- [ ] Unknown `binding_name` returns 404.
- [ ] Playwright `new-issue.spec.ts`: click "+ New Issue" → modal opens → fill title + pick a skill → submit → new card visible in Todo column → reload → still there.
- [ ] `web/api/tests/test_issue_create.py` covers happy path + each validation failure.
- [ ] POST body containing a `state` field is rejected with 400 (`state` is server-set to `'todo'` only; clients cannot pre-set).

## Verification

```
cd /home/james/symphony && uv run pytest && \
cd web/frontend && pnpm test:e2e
```

## Blocked by

- #012
