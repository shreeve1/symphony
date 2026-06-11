---
id: 022
title: Restart-time Run reconciliation + run-log retention
status: review
blocked_by: [020]
parent: null
priority: 0
created: 2026-06-10
---

## What to build

Two operational guards from ADR-0005's accepted-costs paragraph:

1. **Restart-time Run reconciliation** — on Symphony startup, any
   `run.state IN ('queued', 'running')` is reaped to a synthetic
   `failed` row with `verdict='blocked'` and
   `summary='restart-orphan: reaped at <iso8601>'`. The owning Issue's
   `latest_run_state` projection is recomputed. Persistent worktrees
   for orphaned runs are LEFT INTACT (operator inspects); a comment is
   appended to the issue: "Run reaped on restart at <ts>; worktree
   preserved."
2. **Run-log retention** — a background reaper deletes
   `/var/lib/symphony/runs/<id>.log` files older than 90 days OR beyond
   the most-recent 100 per Issue (whichever cuts first). Runs DB rows
   survive; only the disk logs are pruned. Reaper runs once at startup
   and every 24h thereafter. `log_path` column updated to NULL when the
   file is reaped.

Both jobs log structured lines so the existing `journalctl` queries in
`CLAUDE.md` see them.

## Acceptance criteria

- [ ] `tests/test_run_reconcile.py`: seed DB with rows in queued/running, start the engine, assert all become failed/blocked with the synthetic summary and an "orphan" comment on each parent issue.
- [ ] Persistent worktrees (`worktree_active=true`) survive reconciliation (assert path still exists in fixture).
- [ ] `tests/test_log_retention.py`: create 150 logs across 3 issues with mixed timestamps; run the reaper; assert ≤100 logs per issue, none older than 90 days, `log_path=NULL` on reaped rows.
- [ ] Reaper invoked once at startup AND scheduled every 24h (test asserts via the existing scheduler hook).
- [ ] `journalctl -u symphony-host.service | grep -E 'run_reconcile_(begin|done)' && grep -E 'log_retention_(begin|done)'` produces matching pairs.

## Verification

```
cd /home/james/symphony && uv run pytest
```

## Blocked by

- #020 (engine integration must be live before reconcile semantics matter)
