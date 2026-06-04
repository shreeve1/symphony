---
id: 006
title: git-ref plan→build handoff
status: in-progress
blocked_by: [4]
updated: 2026-06-04
actor: ralph
parent: null
priority: 0
created: 2026-06-04
---

## What to build

Under worktree-per-run with local landing, a plan Run's `plans/<slug>.md`
artifact lives on an ephemeral branch that is torn down and never merged, so a
build Run branched off base would never see it. Resolve the handoff entirely in
git: the plan-handoff comment records the plan Run's **branch ref** instead of an
absolute filesystem path, and the build Run creates its worktree off that plan
branch instead of base. Reuse the existing handoff plumbing
(`_PLAN_HANDOFF_MARKER`, `_plan_path_from_comments`) — change only the payload it
carries. The plan artifact rides along on the branch, so the build worktree still
finds `plans/<slug>.md` where the path validator (`_validate_issue_plan_path`,
`scheduler.py:336`) expects it.

See `docs/adr/0003-worktree-per-run-with-global-concurrency-cap.md`.

## Acceptance criteria

- [ ] A plan Run posts a handoff comment carrying its branch ref (not a filesystem path).
- [ ] A build Run reads that comment and creates its worktree off the plan branch.
- [ ] `plans/<slug>.md` resolves inside the build worktree and passes `_validate_issue_plan_path`.
- [ ] `_PLAN_HANDOFF_MARKER` / `_plan_path_from_comments` are reused; only the payload changed.
- [ ] Plan→build handoff covered end-to-end by a test, suite green.

## Verification

`uv run pytest`

## Blocked by

- Blocked by #4
