---
id: 115
title: Carry auto_land through the create/patch API
status: pending
blocked_by: [114]
locks: [web-api]
priority: 1
created: 2026-06-24
---

## What to build

Per ADR-0023, persist `issue.auto_land` through the create/patch API — the path the
`/podium-issues` slicer (120) calls to stamp slicer-authored issues.

- **API** (`web/api/main.py`): add `auto_land: bool = False` to `IssueCreate` and the
  patch model (`IssuePatch`); persist on create/update. Omitted → `False` (the
  default), so UI/operator-created issues are never auto-land.
- Follow the existing boolean-field convention (`worktree_active`,
  `approval_required`) for validation and persistence — no new machinery.
- Expose `auto_land` on the GET issue payload (`_row`) so it round-trips and the
  scheduler/tracker read path (114) sees it.

## Acceptance criteria

- [ ] `POST`/patch accept and persist `auto_land`; omitted → `False`.
- [ ] GET issue payload includes `auto_land`.
- [ ] An operator/UI-created issue (no `auto_land` in the body) is `False`.

## Verification

`uv run pytest web/api/tests/test_issue_create.py web/api/tests/test_issue_patch.py -q`
