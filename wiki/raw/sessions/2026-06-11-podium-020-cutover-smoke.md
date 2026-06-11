# Session Capture: #020 trading→Podium cutover smoke + run-log finalization bug

- Date: 2026-06-11
- Purpose: Perform the operator-driven cutover smoke that gated #020, and close the issue. The smoke surfaced a production-only crash in Podium run finalization that was fixed in-session.
- Scope: Captured the root cause, the fix, the new run-log location convention, and the cutover milestone. Excluded routine progress chatter and env-file contents.

## Durable Facts

- The `trading` binding is live on Podium as of 2026-06-11. The running `symphony-host.service` process predated the `tracker: podium` edit to `bindings.yml`, so a restart was required to activate the cutover. — Evidence: `bindings.yml:63-65`, `journalctl symphony_started code_sha=8eb4aa6 bindings=2`
- Production bug (fixed): `PodiumTrackerAdapter.db_path` defaulted to `None` and `main._build_binding_runtime` constructs the adapter without it. `scheduler._start_run_record` reads `getattr(adapter, "db_path", None)` directly and, on `None`, fell back to `RUN_LOG_ROOT` = `/var/lib/symphony/runs`, which does not exist and is not writable by the service user. `_write_run_log`'s `mkdir` then raised `PermissionError`, crashing `_finish_run_record`. Result: the `run` row was never finalized (stuck `state=running`, null verdict/summary/tokens/log) and the issue reached In Review only via the stale-running reconciler. — Evidence: `journalctl` traceback at `scheduler.py:478`→`399`, `tracker_podium.py:77`, `main.py:75-81`, `scheduler.py:438-439`
- Fix (commit `8eb4aa6`): resolve `db_path` in `PodiumTrackerAdapter.__post_init__` (`self.db_path = self.db_path or resolve_db_path()`) so it is always concrete and the run-log root co-locates with the resolved DB. — Evidence: `tracker_podium.py:__post_init__`, `git show 8eb4aa6`
- New convention: Podium run logs live beside the active `podium.db` at `<db parent>/runs/<id>.log` (currently `/home/james/symphony/runs/<id>.log` in fallback mode), NOT at the `/var/lib/symphony/runs` default — the default only applies once a writable `/var/lib/symphony` exists. The `RUN_LOG_ROOT` default in `web/api/db.py:11` does not itself follow the `resolve_db_path` fallback. — Evidence: `web/api/db.py:8-22`, run 6 `log_path=/home/james/symphony/runs/6.log`
- The pre-existing mocked dispatch test masked this bug by both passing an explicit `db_path` AND monkeypatching `scheduler.RUN_LOG_ROOT` to tmp, so it never exercised the production construction path. A regression test (`test_trading_podium_dispatch_logs_colocate_with_resolved_db`) now builds the adapter as `main` does and fails without the fix. — Evidence: `tests/test_trading_podium_dispatch.py`
- Smoke result: issue 17 (read-only liveness task, filed by direct `podium.db` insert since the Podium web UI/API was not running) dispatched a real `pi` run; run 6 reached `state=succeeded`, `verdict=review`, log written to disk, `comments_md` summary + `context_md` detail populated, in ~59s. Trading repo was not mutated. — Evidence: `podium.db` run 6 / issue 17, `/home/james/symphony/runs/6.log`
- cost/token columns stay null when the agent emits no `SYMPHONY_COST_USD`/`SYMPHONY_INPUT_TOKENS`/`SYMPHONY_OUTPUT_TOKENS` markers (the minimal read-only task did not). The scrape mechanism is covered by the mocked dispatch test, not the live smoke.

## Decisions

- James approved both live restarts at the moment of action, and approved filing the smoke ticket by direct `podium.db` insert (read-only task) given the UI was down. — Evidence: in-session AskUserQuestion approvals
- The formatter drift (rogue `ruff format` reflow on `scheduler.py`/`tracker_podium.py`/the test) was discarded rather than committed: the repo does not enforce ruff-format (35 committed files non-conforming) and the reflow did not trace to #020. — Evidence: `git stash` + `ruff format --check .` showed 35 files would reformat

## Evidence

- `tracker_podium.py` — adapter `db_path` default and `__post_init__` fix
- `scheduler.py:398-440,463-478` — `_write_run_log`, `_start_run_record`, `_finish_run_record`
- `web/api/db.py:8-22` — `DEFAULT_DB_PATH`, `FALLBACK_DB_PATH`, `RUN_LOG_ROOT`, `resolve_db_path`
- `tests/test_trading_podium_dispatch.py` — masking test + new regression test
- commits `12289da`, `8eb4aa6`, `eb1a706` (local-only; not pushed to `github-personal`)

## Exclusions

- No contents of `/home/james/symphony-host.env`.
- Full journal spam (thousands of `dispatch_completed reason=no-candidates` lines during the crash window) not archived; rate settled to 0/10s after the failed dispatch — judged a transient crash-retry storm, not a standing bug.

## Open Questions And Follow-Ups

- Seed issue 3 / run 5 are left in a stale state (run 5 stuck `running`) from the pre-fix crash — cosmetic seed noise, safe to clean later.
- Should `RUN_LOG_ROOT` in `web/api/db.py` be made to follow the same `resolve_db_path` fallback for defense-in-depth (so the Plane-adapter path and any future caller can't hit the unwritable default)? Out of #020 scope; candidate for #024 defensive hardening.
- Commits are local-only; push to `github-personal` is pending James.
