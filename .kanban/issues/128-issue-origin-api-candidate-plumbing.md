---
id: 128
title: Carry origin through API create + CandidateIssue plumbing
status: pending
blocked_by: [127]
parent: null
priority: 0
created: 2026-07-02
---

## What to build

Thread the `origin` column through the issue-create API and into the scheduler's
`CandidateIssue`, so the terminal handler (issue #129) can read it. Caller
declares origin explicitly (Option B) with a server-side backstop (Option A).

- `web/api/main.py`:
  - Add `origin: str | None = None` to the `IssueCreate` model.
  - In the create handler, resolve the effective origin:
    - if `issue.origin` is provided, use it (must be `'operator'` or
      `'patrol'` — invalid value returns 422 via the DB CHECK / validation);
    - else if `issue.origin` is unset but `issue.external_id` is not None →
      coerce to `'patrol'` (the backstop for un-migrated external callers);
    - else default `'operator'`.
  - Persist `origin` in the INSERT column list + values.
- `tracker_types.py`: add `origin: str = "operator"` field to `CandidateIssue`.
- `tracker_podium.py`: in `list_candidates()`, populate
  `origin=str(issue.get("origin") or "operator")` on the `CandidateIssue(...)`
  construction.

No behavior change to the scheduler yet — that's #129. This slice only makes the
value flow create → DB → candidate.

## Acceptance criteria

- [ ] `IssueCreate` accepts an optional `origin` field.
- [ ] Create with explicit `origin='patrol'` persists `'patrol'`.
- [ ] Create with no `origin` but a non-null `external_id` persists `'patrol'`
      (backstop).
- [ ] Create with no `origin` and no `external_id` persists `'operator'`.
- [ ] `CandidateIssue` exposes `origin` (defaults `'operator'`), populated from
      the issue row in `tracker_podium.list_candidates()`.

## Verification

`PATH="$HOME/.local/bin:$PATH" uv run pytest web/api/tests/test_issue_create.py -q`

## Blocked by

- Blocked by #127
