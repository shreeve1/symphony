---
title: Podium #022 — restart Run reconciliation and run-log retention
type: analysis
status: promoted
created: 2026-06-11
updated: 2026-06-11
sources:
  - scheduler.py
  - tracker_podium.py
  - tests/test_run_reconcile.py
  - tests/test_log_retention.py
confidence: high
tags: [podium, run-table, restart-reconcile, log-retention, operations, scheduler]
---

# Podium #022 — restart Run reconciliation and run-log retention

## Summary

#022 implements the ADR-0005 operational guards for Podium Run durability: startup reaps orphaned `run.state IN ('queued','running')` rows, and a retention pass prunes only log files while preserving Run DB rows. The scheduler exposes `run_reconcile_begin/done` and `log_retention_begin/done` structured log pairs for journal checks. [source: scheduler.py#1332-1367] [source: tracker_podium.py#355-472]

## Startup Run reconciliation

`scheduler.reconcile_startup(...)` now calls `reconcile_orphaned_runs(...)` before legacy stale-running issue reconciliation, then calls `run_log_retention(...)`. The Podium adapter hook is optional: non-Podium adapters without the method are no-ops. [source: scheduler.py#1332-1367] [source: scheduler.py#1420-1435]

`PodiumTrackerAdapter.reconcile_orphaned_runs(...)` selects Run rows still `queued` or `running` for its binding, sets each row to `state='failed'`, `verdict='blocked'`, `summary='restart-orphan: reaped at <iso8601>'`, `exit_code=COALESCE(exit_code, 1)`, and `ended_at=<iso8601>`. It refreshes the owning Issue's latest-Run projection, marks the Issue `blocked`, and appends `Run reaped on restart at <ts>; worktree preserved.` to `comments_md`. It does not delete or modify `worktree_path` contents. [source: tracker_podium.py#355-415]

Regression coverage seeds queued/running rows, runs startup reconciliation, verifies failed/blocked summaries and parent Issue orphan comments, and asserts a persistent worktree directory still exists. [source: tests/test_run_reconcile.py#102-148]

## Run-log retention

`scheduler.LOG_RETENTION_INTERVAL` is 24 hours. Startup invokes retention once through `reconcile_startup(...)`; `run_loop(...)` schedules later retention passes when `now >= next_log_retention_at`. [source: scheduler.py#74] [source: scheduler.py#1434-1435] [source: scheduler.py#1547-1566]

`PodiumTrackerAdapter.prune_run_logs(...)` groups `run.log_path` rows by Issue, ordered newest first by `started_at DESC, id DESC`. A log is reaped if its file mtime is older than 90 days or if it is beyond the most recent 100 logs for that Issue. The file is deleted when present, and the Run row survives with `log_path=NULL`. [source: tracker_podium.py#417-472]

Regression coverage creates 150 logs across 3 Issues: 120 young logs for one Issue, 20 logs older than 90 days for another, and 10 recent logs for a third. It asserts 40 reaped rows, at most 100 remaining logs per Issue, no retained file older than 90 days, and `log_path=NULL` on reaped rows. Separate tests assert startup invocation and the 24-hour scheduler hook. [source: tests/test_log_retention.py#100-196]

## Operational logging

The scheduler logs:

- `run_reconcile_begin binding=<name>` / `run_reconcile_done binding=<name> reaped=<n>`
- `log_retention_begin binding=<name>` / `log_retention_done binding=<name> pruned=<n>`

Coverage verifies both log pairs through `caplog`. [source: scheduler.py#1344-1347] [source: scheduler.py#1362-1366] [source: tests/test_run_reconcile.py#151-174]

## Verification

Implementation verification passed with `uv run pytest`: 552 passed, 1 skipped. Fresh review inspected `git diff d8af994507f562d46383287166e1551002433270 HEAD`, read every changed file, ran the same verification command, and returned `RALPH_REVIEW: PASS`.
