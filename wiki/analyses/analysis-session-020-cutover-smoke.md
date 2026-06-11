---
title: "#020 trading→Podium cutover smoke and run-log finalization bug"
type: analysis
status: promoted
created: 2026-06-11
updated: 2026-06-11
sources:
  - wiki/raw/sessions/2026-06-11-podium-020-cutover-smoke.md
  - tracker_podium.py
  - scheduler.py
  - web/api/db.py
  - tests/test_trading_podium_dispatch.py
confidence: high
tags: [podium, cutover, trading, run-log, dispatch, debugging, "#020"]
---

# #020 trading→Podium cutover smoke and run-log finalization bug

## Summary

The #020 cutover flips the `trading` binding to `tracker: podium`. Implementation
and mocked tests had landed, but the operator-driven smoke had not run. Performing
it surfaced a **production-only crash** in Podium run finalization that the mocked
test could not catch. The bug was fixed in-session (`8eb4aa6`) and the smoke then
passed end-to-end, closing #020.

## Root cause

`PodiumTrackerAdapter.db_path` defaults to `None`, and
`main._build_binding_runtime` constructs the adapter **without** a `db_path`
(`main.py:75-81`). `connect()` masks this for DB I/O by falling back to
`resolve_db_path()`, but `scheduler._start_run_record` reads `adapter.db_path`
**directly** (`scheduler.py:438-439`):

```python
adapter_db_path = getattr(adapter, "db_path", None)
run_log_root = Path(adapter_db_path).parent / "runs" if adapter_db_path is not None else RUN_LOG_ROOT
```

With `db_path is None`, the run-log root fell to `RUN_LOG_ROOT`
(`/var/lib/symphony/runs`, `web/api/db.py:11`) — a directory that does not exist
and is not writable by the service user. At finalization,
`_finish_run_record` → `_write_run_log`'s `mkdir(parents=True)` raised
`PermissionError`. Consequences:

- the `run` row was never finalized (stuck `state=running`, null
  verdict/summary/tokens/log_path);
- the issue reached In Review only via the **stale-running reconciler**, not the
  normal completion path.

This refines [C-0062] (run logs → `runs/{id}.log`) and intersects [C-0067]
(DB-path fallback): `RUN_LOG_ROOT` did **not** mirror `resolve_db_path`'s
fallback, so the db resolved to the repo root while logs targeted
`/var/lib/symphony`.

## Fix

Resolve `db_path` in `PodiumTrackerAdapter.__post_init__` so it is always
concrete:

```python
if self.db_path is None:
    self.db_path = resolve_db_path()
```

Now `_start_run_record` computes `run_log_root = <db parent>/runs`, co-located
and writable (`/home/james/symphony/runs` in fallback mode). Commit `8eb4aa6`.

## Why the mocked test missed it

`test_trading_podium_dispatch_records_run_log_and_context` both passes an
explicit `db_path=db_path` AND monkeypatches `scheduler.RUN_LOG_ROOT` to a tmp
dir — doubly avoiding the production construction path. The new regression test
`test_trading_podium_dispatch_logs_colocate_with_resolved_db` builds the adapter
the way `main` does (no `db_path`, no `RUN_LOG_ROOT` override, `PODIUM_DB_PATH`
pointed at tmp) and asserts the log lands at `<db parent>/runs/<id>.log`; it
fails without the fix. **Lesson:** integration coverage for dispatch must
exercise the real adapter-construction path, not a pre-wired adapter.

## Smoke evidence

After reloading the fix, smoke issue 17 (read-only liveness task, filed by direct
`podium.db` insert because the Podium web UI/API was not running) dispatched a
real `pi` run. Run 6: `state=succeeded`, `verdict=review`,
`log_path=/home/james/symphony/runs/6.log` (stdout+stderr on disk),
`comments_md` summary block + `context_md` detail populated, ~59s end to end. The
trading repo was not mutated (agent obeyed the read-only scope). `uv run pytest`:
520 passed, 1 skipped.

## Convention established

Podium run logs live beside the active `podium.db` at `<db parent>/runs/<id>.log`,
not at the `/var/lib/symphony/runs` default — the default applies only once a
writable `/var/lib/symphony` exists.

## Follow-ups

- Consider making `RUN_LOG_ROOT` follow `resolve_db_path`'s fallback for
  defense-in-depth (candidate for #024 hardening).
- Seed issue 3 / run 5 left stale (`running`) by the pre-fix crash — cosmetic.
- Commits `12289da`, `8eb4aa6`, `eb1a706` are local-only; push pending.

[C-0062]: ../CLAIMS.md
[C-0067]: ../CLAIMS.md
