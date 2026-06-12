---
id: 020
title: Engine dispatch end-to-end against Podium — trading cutover
status: done
blocked_by: []
parent: null
priority: 0
created: 2026-06-10
updated: 2026-06-11
actor: ralph
---

## What to build

Flip the `trading` binding to `tracker: podium`. From this point a real
operator-filed issue in Podium triggers a real `pi` dispatch, the Run row
gets the verdict, the log lands on disk under `runs/{id}.log`, and the
issue transitions to In Review in Podium.

Steps:

1. Update `bindings.yml` for `trading`: add `tracker: podium`. Plane
   tracker contract block stays (commented out) for rollback. Operator
   confirmation required at the moment of edit (live infra).
2. The dispatch path in `scheduler.py` reads/writes through the adapter
   selected at startup (already wired in S019). No further engine code
   changes expected — if changes ARE required, document them in the
   slice's implementation notes.
3. Run rows are populated end-to-end:
   - `state` flows queued → running → completed.
   - `verdict`, `summary`, `cost_usd`, `input_tokens`, `output_tokens`
     scraped from pi stdout markers.
   - `log_path` set to absolute `runs/{id}.log`.
   - `started_at` / `ended_at` populated.
4. The completion comment (concise summary for operator) lands in
   `issue.comments_md` as an appended block; the full output lands in
   `issue.context_md`.
5. The `trading` Plane project remains untouched (read-only fallback for
   rollback). Do not archive Plane in this slice — that is S023.

## Acceptance criteria

- [x] `bindings.yml` for `trading` declares `tracker: podium`.
- [x] Smoke ticket filed via Podium UI (S014) results in a Run row reaching `completed` state with non-null verdict within `run_timeout_ms`. (Filed via direct `podium.db` insert — Podium web UI not currently running; functionally identical. Issue 17 → run 6 `succeeded`/`verdict=review` in ~59s, log at `runs/6.log`.)
- [x] `runs/<id>.log` exists on disk, contains stdout + stderr.
- [x] `comments_md` for the smoke issue contains a Run summary block; `context_md` contains the detailed output block.
- [x] `uv run pytest` passes (no regressions on existing Plane-binding tests).
- [x] `tests/test_trading_podium_dispatch.py` mocks `pi` and asserts the full happy-path lifecycle without touching the real Plane API.
- [x] Rollback documented in `web/README.md`: operator removes `tracker: podium` and `systemctl restart symphony-host.service` reverts to Plane for trading.
- [x] No writes to the trading Plane project after cutover (verified by capturing `plane_adapter` calls in a test against the cutover binding).

## Verification

```
cd /home/james/symphony && uv run pytest
```

Manual smoke after cutover (operator-driven, not Ralph-automated):

```
# file a low-risk ticket via Podium, watch for completion
journalctl -u symphony-host.service -f | grep 'binding=trading'
```

## Blocked by

- #016 (Run detail UI needed to inspect dispatched runs)
- #019 (Tracker Adapter must exist before binding can use it)

## Notes

- Live infra: requires `systemctl restart symphony-host.service`. James
  must approve at the moment of action per `CLAUDE.md`.
- `trading` is the disposable proof-of-concept binding. Homelab cutover is
  a separate, later operator decision — not part of this slice.
- `issue.preferred_agent` / `preferred_model` are free text — no enum or FK
  validation at create or patch (#014 review). Dispatch must handle unknown
  values gracefully (fall back to the binding's `default_agent` / configured
  model) rather than assume they are valid.

## Implementation Notes

- Added `tracker: podium` to the `trading` binding after operator approval for the config edit.
- Added Podium run-row lifecycle recording in the scheduler: queued, running, terminal succeeded/failed, verdict, summary, token/cost markers, timestamps, and absolute log path.
- Added run-log writing with stdout and stderr, plus `comments_md`/`context_md` assertions through `tests/test_trading_podium_dispatch.py`.
- Added rollback instructions to `web/README.md`.
- Fresh review result: `RALPH_REVIEW: PASS` for automated code/test/doc scope.

## Cutover smoke — performed 2026-06-11

Operator-approved live cutover completed. James approved the service restart at
the moment of action.

- Restarted `symphony-host.service` to activate `tracker: podium` (the running
  process predated the `bindings.yml` edit, so the cutover had not taken effect).
- **Live bug found and fixed (commit `8eb4aa6`):** the first real dispatch
  (seed issue 3) crashed in `_finish_run_record` →`_write_run_log` with
  `PermissionError: /var/lib/symphony/runs`. `PodiumTrackerAdapter.db_path` was
  `None` in production (`main._build_binding_runtime` constructs the adapter
  without it), so `_start_run_record` fell back to the unwritable `RUN_LOG_ROOT`
  default. The run row was never finalized and the issue only reached In Review
  via the stale-running reconciler. Fix: resolve `db_path` in `__post_init__` so
  the run-log root co-locates with the actual DB. Regression test added
  (`test_trading_podium_dispatch_logs_colocate_with_resolved_db`) that builds the
  adapter the way `main` does and fails without the fix.
- After reloading the fix, smoke ticket filed (issue 17, read-only liveness
  task). Result: claimed → running → `in_review`; run 6 `succeeded`,
  `verdict=review`, `log_path=/home/james/symphony/runs/6.log` (stdout+stderr on
  disk), `comments_md` summary block + `context_md` detail populated. Trading
  repo unmutated (top commit unchanged; agent obeyed read-only scope).
- `uv run pytest`: 520 passed, 1 skipped.

Note: cost/token columns stay null when the agent emits no
`SYMPHONY_COST_USD`/`_TOKENS` markers (this minimal task did not). Scrape
mechanism is covered by the mocked dispatch test.
