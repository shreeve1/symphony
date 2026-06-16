---
title: "Question Park verdict/schema drift exposed by Issue #25"
type: analysis
status: promoted
created: 2026-06-15
updated: 2026-06-15
sources:
  - wiki/raw/sessions/2026-06-15-issue-max-question-verdict-drift.md
  - scheduler.py
  - web/api/schema.py
  - tests/test_scheduler.py
confidence: high
tags: [podium, question-park, dispatch, run, schema, incident]
---

# Question Park verdict/schema drift exposed by Issue #25

Issue `25` (`binding=symphony`, title `issue max`) exposed a live mismatch between the Question Park scheduler path and the Podium SQLite schema. The agent exited cleanly and emitted `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END`, but the Run row stayed `running` because the scheduler tried to persist `verdict="question"` and SQLite rejected it under the existing `done|review|blocked` CHECK constraint [source: wiki/raw/sessions/2026-06-15-issue-max-question-verdict-drift.md].

## What happened

The read-only DB snapshot showed Issue `25` as `state='in_review'` with `latest_run_id=36` and `latest_run_state='running'`. Run `36` had `state='running'`, `ended_at=NULL`, agent `pi`, provider `openai-codex`, model `gpt-5.5:high`, and skill `grill-me` [source: wiki/raw/sessions/2026-06-15-issue-max-question-verdict-drift.md].

Scheduler journal showed the real Run lifecycle: `resume_skipped`, `issue_claimed`, `pi_rpc_dispatch`, then `agent_exited issue_id=25 exit_code=0 duration_ms=69190 timed_out=false`. Immediately after clean exit, `_finish_run_record` raised `sqlite3.IntegrityError: CHECK constraint failed: verdict IS NULL OR verdict IN ('done','review','blocked')`. Scheduler then logged `state_transitioned issue_id=25 state=in-review reason=stale-running` [source: wiki/raw/sessions/2026-06-15-issue-max-question-verdict-drift.md].

The run log confirmed the agent had parked a clarification question about adding a Maximize/Restore button to the Issue flyout. This was not a still-running agent process; it was a finalization failure after a clean Question Park output [source: wiki/raw/sessions/2026-06-15-issue-max-question-verdict-drift.md].

## Root cause

The Question Park branch in `scheduler.py` calls `_finish_run_record(... state="succeeded", verdict="question", summary=question, ...)` before posting the question comment and transitioning the Issue to `in_review` [source: scheduler.py].

The Podium schema still constrains `run.verdict` and `issue.latest_verdict` to `NULL` or `done|review|blocked`; `question` is not valid [source: web/api/schema.py]. Existing Question Park tests verify in-review parking and comment text, but do not exercise the Podium SQLite CHECK constraint path [source: tests/test_scheduler.py].

## User-facing symptom

Podium can show an Issue in `in_review` while its latest Run still says `running` when Question Park finalization fails. The Issue state comes from stale-running fallback transition, not from successful Run completion [source: wiki/raw/sessions/2026-06-15-issue-max-question-verdict-drift.md].

## Follow-up options

Two compatible fix directions exist; choose one before mutating live state:

1. Add `question` to the persisted verdict vocabulary for both runtime schema and Alembic migrations, then cover Question Park through `PodiumTrackerAdapter` and SQLite.
2. Keep persisted verdicts limited to `done|review|blocked`, map Question Park to `verdict='review'`, and represent the park outcome via state/reason/summary/comment.

Either path needs a regression test that exercises Question Park against Podium SQLite constraints [source: wiki/raw/sessions/2026-06-15-issue-max-question-verdict-drift.md].

## Claims

C-0211 in [CLAIMS.md](../CLAIMS.md).
