---
id: 036
title: Podium — 14-day archived-issue retention purge
status: review
blocked_by: [034]
parent: null
priority: 0
created: 2026-06-12
updated: 2026-06-12
actor: ralph
---

## What to build

Hard-delete archived issues after two weeks, per
`wiki/analyses/podium-issue-archive-design.md`. Opportunistic sweep, no
scheduler: run the purge (a) once at API startup and (b) after every PATCH
that transitions an issue to `archived`. Window is a hardcoded constant
`PURGE_AFTER_DAYS = 14` in `web/api/main.py` — no config knob. The clock is
`updated_at` (there is no `archived_at` column by design): eligible rows are
`state = 'archived' AND updated_at < now − 14 days`.

**FK-safe delete order.** `PRAGMA foreign_keys = ON` (`web/api/db.py:51`) plus
`run.issue_id → issue` and `issue.latest_run_id → run` force this order per
eligible issue, all inside one transaction:

1. Collect the issue's run `log_path` values.
2. `UPDATE issue SET latest_run_id = NULL`.
3. `DELETE FROM run WHERE issue_id = ?`.
4. `DELETE FROM issue WHERE id = ?`.

After commit, best-effort `unlink` each collected log file — a missing or
undeletable file is logged and skipped, never an error. Defensively call
`remove_worktree` if a worktree still exists for a purged issue (normally
#035 has already torn it down). Log one structured summary line per sweep
(`archive_purge` with purged count; skip the line when nothing purged).
Purged issues are gone from the board on the next fetch; no WS event
contract exists for deletions, so none is required.

## Acceptance criteria

- [ ] Archived issue with `updated_at` older than 14 days is deleted — issue row, its run rows, and its run log files all gone — with `PRAGMA foreign_keys = ON` active in the test connection.
- [ ] Archived issue younger than 14 days, and non-archived issues of any age, survive the sweep untouched.
- [ ] Sweep runs at API startup (test via the FastAPI test client lifespan) and after a PATCH to `archived`; PATCH response is unaffected by the sweep.
- [ ] Missing log file on disk does not abort the purge; remaining eligible issues still purge.
- [ ] A failure mid-purge rolls back the transaction for that issue (no orphaned runs, no issue with nulled `latest_run_id` left behind).
- [ ] Purge of an issue whose worktree still exists removes the worktree (defensive path).

## Verification

```
cd /home/james/symphony && python3 -m pytest
```

## Blocked by

- Blocked by #034 (`archived` state must exist). Independent of #035 — can run in parallel after #034.
