---
id: 118
title: Review-phase selection + dispatch (in_review coding issues, marker-gated)
status: pending
blocked_by: [108, 116]
locks: [scheduler]
priority: 1
created: 2026-06-24
---

## What to build

Per ADR-0023, dispatch a fresh review run for a coding issue after its implement run
parks it in `in_review`. The trigger is a **second candidate-selection source**, NOT
an inline same-tick dispatch and NOT a "stays running" issue — candidate selection
today only picks `STATE_TODO` (`scheduler/__init__.py:1263` bails "state-changed"
otherwise), so the review run must be selected from `in_review` through the normal
dispatch machinery. This slice is selection + dispatch only; the terminal outcome
(pass/fail/land) is 119.

- Leave the implement terminal handler UNCHANGED: an implement run finishing a coding
  issue still parks it in `in_review` (today's `agent-marker-review` path).
- Add a review-eligibility source to candidate selection: a `type: coding` issue in
  `in_review` whose `comments_md` has **no** `### Symphony Review` marker is eligible
  for a **review dispatch**. Marker present ⇒ already reviewed ⇒ not re-selected
  (this is what makes the phase idempotent across ticks).
- Dispatch the review run through the existing render→run→classify machinery, but:
  - render with `REVIEW_PREAMBLE` (116) instead of the implement prompt;
  - re-enter the SAME deterministic `worktree_dir(repo, binding, issue_id)` (108's
    worktree — do not create a new one); remote bindings (no worktree, cap 1)
    re-enter `binding.repo_path`, same as the implement run;
  - append the `### Symphony Review (n)` marker to `comments_md` at dispatch (so the
    next tick won't re-select it; counter pattern mirrors `_count_commit_redispatches`
    at `web/api/main.py:1816`, but scheduler-owned).
  - Review run agent = binding `default_agent` (pi); reuse the implement run's
    model/effort.
- Each review run independently acquires/releases the `run_cap` semaphore and obeys
  the ADR-0021 lock gate — it is an ordinary dispatch, not a held inline phase.
- **Scope:** coding bindings only. Infra issues in `in_review` are NOT review-eligible
  (ADR-0020 `auto_close_on_verified` owns their close).

## Acceptance criteria

- [ ] A coding issue in `in_review` with no `### Symphony Review` marker is selected
      and dispatched as a review run (REVIEW_PREAMBLE, same `worktree_dir`).
- [ ] After dispatch the issue carries a `### Symphony Review (n)` marker and is not
      re-selected for review on the next tick.
- [ ] Infra issues in `in_review` are never review-dispatched.
- [ ] The review run uses the normal semaphore/lock path (not a held inline phase).

## Verification

`uv run pytest tests/test_scheduler.py -q`
