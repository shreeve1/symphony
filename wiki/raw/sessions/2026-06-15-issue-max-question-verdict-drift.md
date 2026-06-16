# Session Capture: Issue max Question Park verdict drift

- Date: 2026-06-15
- Purpose: Capture the verified root cause for the `symphony` binding Issue titled `issue max` showing `in_review` while its latest Run still showed `running`.
- Scope: Read-only troubleshooting evidence from Podium SQLite, scheduler journal, run log, and source/schema comparison. No DB writes, service restarts, env reads, or tracker mutations were performed.

## Durable Facts

- Podium Issue `25` on binding `symphony`, title `issue max`, had `state='in_review'`, `latest_run_id=36`, and `latest_run_state='running'` after dispatch. Evidence: read-only SQLite query against `resolve_db_path()` (`/home/james/symphony/podium.db`).
- Run `36` for Issue `25` started at `2026-06-15T02:02:50.644122+00:00`, used agent `pi`, provider `openai-codex`, model `gpt-5.5:high`, skill `grill-me`, and remained `state='running'` with `ended_at=NULL` in the database. Evidence: read-only SQLite query against `run where id=36`.
- Scheduler journal shows the agent exited cleanly: `agent_exited issue_id=25 exit_code=0 duration_ms=69190 timed_out=false`, followed by `dispatch_failed error=CHECK constraint failed: verdict IS NULL OR verdict IN ('done','review','blocked')`. Evidence: `journalctl -u symphony-host.service --since='2026-06-15 02:02:30 UTC' --until='2026-06-15 02:04:20 UTC'` filtered to non-`no-candidates` lines.
- After the `dispatch_failed` exception, scheduler logged `state_transitioned issue_id=25 state=in-review reason=stale-running`, explaining why the Issue moved to `in_review` while the Run projection remained `running`. Evidence: same journal slice.
- `/home/james/symphony/runs/36.log` contains multiple `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END` blocks asking whether to implement a Maximize/Restore button for the issue flyout. Evidence: `tail -n 160 /home/james/symphony/runs/36.log`.
- `scheduler.py` handles a parsed question by calling `_finish_run_record(... state="succeeded", verdict="question", ...)`. Evidence: `scheduler.py` around the Question Park branch.
- `web/api/schema.py` constrains both `issue.latest_verdict` and `run.verdict` to `NULL` or `done|review|blocked`; `question` is not allowed. Evidence: `web/api/schema.py` table definitions.
- Existing test `test_question_marker_parks_issue_in_review` covers the in-review transition and comment body, but does not assert Podium run-row persistence against the SQLite CHECK constraint. Evidence: `tests/test_scheduler.py`.

## Decisions

- No live mutation was performed during troubleshooting. Corrective options remain separate: code/schema fix, run reconciliation, or operator reply/re-dispatch after safe state repair.

## Evidence

- `scheduler.py` — Question Park branch attempts to finish Run with `verdict="question"`.
- `web/api/schema.py` — Run and latest-verdict CHECK constraints exclude `question`.
- `tests/test_scheduler.py` — existing Question Park test misses the Podium SQLite constraint path.
- `journalctl -u symphony-host.service` slice — clean agent exit followed by SQLite CHECK failure and stale-running in-review transition.
- `/home/james/symphony/runs/36.log` — agent output was a Question Park block, not a long-running process.

## Exclusions

- No contents of `/home/james/symphony-host.env` were read or captured.
- No secret values, cookies, auth headers, or API credentials were captured.
- No full transcript or raw user-pasted content was captured.
- No DB writes, service restarts, systemd edits, or Podium state mutations were performed.

## Open Questions And Follow-Ups

- Fix schema/code mismatch: either allow `question` in `run.verdict` / `issue.latest_verdict` via schema + Alembic + tests, or map Question Park to an existing verdict such as `review` while preserving `reason=agent-question-park` semantics.
- Add a regression test that exercises Question Park through `PodiumTrackerAdapter` and SQLite constraints.
- Repair or reconcile live Issue `25` / Run `36` only after choosing the fix path and applying normal live-mutation approval gates.
