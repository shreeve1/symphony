---
id: 128
title: Carry origin through API create + CandidateIssue plumbing
status: done
blocked_by: [127]
parent: null
priority: 0
created: 2026-07-02
updated: 2026-07-02
actor: ralph
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

- [x] `IssueCreate` accepts an optional `origin` field.
- [x] Create with explicit `origin='patrol'` persists `'patrol'`.
- [x] Create with no `origin` but a non-null `external_id` persists `'patrol'`
      (backstop).
- [x] Create with no `origin` and no `external_id` persists `'operator'`.
- [x] `CandidateIssue` exposes `origin` (defaults `'operator'`), populated from
      the issue row in `tracker_podium.list_candidates()`.

## Verification

`PATH="$HOME/.local/bin:$PATH" uv run pytest web/api/tests/test_issue_create.py -q`

## Blocked by

- Blocked by #127

## Implementation Notes

Added `origin: Literal["operator", "patrol"] | None = None` to `IssueCreate`
(main.py) — using the `Literal` type means an invalid value is rejected at
validation as 422 (matching the DB CHECK vocabulary) rather than hitting the DB.
The create handler resolves the effective origin before the INSERT: explicit
caller value wins (Option B); else non-null `external_id` → `'patrol'`
(Option A backstop); else `'operator'`. Added `origin` to the INSERT column
list + values. `_row()` already returns every column via `dict(row)`, so the
create/read responses expose `origin` with no extra plumbing.
`CandidateIssue` (tracker_types.py) gained `origin: str = "operator"`, populated
in `tracker_podium.list_candidates()` via `origin=str(issue.get("origin") or
"operator")`. No scheduler behavior change (deferred to #129). Added 5 tests to
`test_issue_create.py` covering default, explicit patrol, external_id backstop,
explicit-wins-over-external_id, and invalid-value-422. Verification
`uv run pytest web/api/tests/test_issue_create.py -q` passes (59 passed, exit 0).
