# Comment is the primitive; reopen is a separate effect

Status: accepted; landed 2026-06-20

## Context

Podium stores all comments as one `comments_md` markdown blob on the issue row,
appended to by three writers: Symphony's in-process coding agent, the operator's
UI, and Temporal patrols. Only the coding agent had a clean path —
`tracker_podium._append_comments` does a plain `UPDATE comments_md` with no side
effects, which is the behavior the operator likes. Every *remote* writer had only
one HTTP door: `POST /api/issues/{id}/reply`, the operator *re-dispatch*
endpoint, which fuses four effects — append, flip `state='todo'`, bump, wake the
scheduler — and is gated to a parked/done issue with no active run (else 409).

Patrols were forced to borrow `/reply`, inheriting effects they never wanted:
every patrol comment (including passing ones) reopened the issue and re-dispatched
a pi agent, comments were mislabeled `### Operator Reply`, and the gate produced
deterministic 409s mid-remediation. This is the C-0281 churn (and the C-0279/
C-0280 self-heal regressions it caused). Root cause is architectural: `/reply`
conflates two orthogonal effects — *appending a comment* and *reopening for
re-dispatch*.

## Decision

Make **Comment the append-only primitive and reopen a separate, explicit
effect.** Add `POST /api/issues/{id}/comment` that mirrors `_append_comments`:
append an attributed block, bump `updated_at`, publish `issue.updated` — **no
state flip, no run-state gate**. It reuses the existing `require_auth` middleware
(Bearer for patrols, cookie for the UI). `/reply` is left exactly as-is (append +
reopen, gated) — the two endpoints are two honest contracts, never one
flag-driven handler.

Patrols repoint `PodiumAdapter.add_comment` from `/reply` to `/comment` and land
under a `### Patrol (<ts>)` header (one header for fail/pass/close; the outcome is
already in the structured body). Reopen-on-failure and close-on-pass become
purely the explicit `update_issue(state=…)` calls already present in
`patrol_plane.py`; the comment no longer carries a reopen side effect, so the
"comment-before-flip" ordering and `_post_comment_tolerating_409` 409-swallowing
stop being load-bearing (regression tests retained as belt-and-suspenders). The
Temporal workflow/activity signatures and the six schedules are untouched — this
is worker-adapter-level only, deployed by one worker restart.

The frontend splitter (`IssueFlyout.tsx`) learns `### Patrol (` as an always-shown
entry boundary.

## Considered options

- **`reopen: bool` flag on `/reply`** — fewer routes, but the gate/404/409 logic
  becomes conditional inside one handler with two personalities. Rejected.
- **Refactor `/reply` to call a shared append helper then transition** — most
  elegant internally, but edits the working, operator-gated `podium-api`
  endpoint for zero external behavior change. Rejected (risk without benefit).
- **Patrol writes SQLite directly (same host)** — worker and `podium-api` are
  co-located on loopback, but the boundary is process/repo, not host; a direct
  writer bypasses `updated_at` monotonicity, the `issue.updated` publish, auth,
  and schema-drift checks, and adds a second writer to one SQLite file. Rejected.

## Consequences

- An **operator "Note" action** (a plain Comment from the UI, no re-run) is now
  *possible* — `/comment` allows it in any state, unlike Reply. The endpoint is
  built; the UI button is **deferred** (YAGNI) until the need is felt. Steer
  already covers operator input during a run; Note's unique value is a durable
  no-re-run note on a parked/done issue.
- Cross-repo: Symphony adds the endpoint + frontend + docs (one gated
  `podium-api` migration-free restart — touches only existing columns); homelab
  repoints the adapter + simplifies the activity helpers (one worker restart).
- Supersedes the C-0281 "deferred durable fix" with the real design.

### Landed (2026-06-20)

Shipped and deployed across all three services. Symphony `POST /api/issues/{id}/comment`
(`web/api/main.py`) + `web/api/tests/test_comment.py` + the `### Patrol (` frontend
splitter; homelab `add_comment` repointed to `/comment` with a worker-stamped
`### Patrol (<iso-ts>)` header. Both suites green (no new failures); both wave diffs
passed an independent pi audit. `podium-api`/`podium-web` restarted (symphony first),
then the patrol worker restarted on `code_sha=8a101eb` (`tracker=podium binding=homelab`).
A live docker patrol confirmed the worker posts to `/comment` (`200`, no `409`, no `/reply`)
with the comment and the failure-reopen now decoupled: the `/comment` POST does not flip
state, and a still-failing check reopens via a separate explicit `update_issue(state=TODO)`.
Pass-no-reopen and close-stays-done are covered by contract tests (no docker check passed
the verification cycle, so those paths were not live-observed). C-0281 is resolved.
