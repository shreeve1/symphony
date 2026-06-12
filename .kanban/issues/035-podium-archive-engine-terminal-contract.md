---
id: 035
title: Podium — archived is engine-terminal: resurrection guard + worktree teardown
status: done
blocked_by: [034]
updated: 2026-06-12
actor: ralph
parent: null
priority: 0
created: 2026-06-12
---

## What to build

The engine side of the archived contract, per
`wiki/analyses/podium-issue-archive-design.md` and the CONTEXT.md Tracker
Contract entry: archived is never an engine Role — the engine never selects
archived work, and post-run it honors archived as terminal (no verdict state
transition, worktree torn down, output discarded).

**Resurrection guard.** `PodiumTrackerAdapter.transition_state`
(`tracker_podium.py:315-324`) is an unconditional UPDATE today: an operator
archiving an issue mid-run gets resurrected when the run finishes and the
engine writes the verdict state. Make the UPDATE conditional —
`WHERE id = ? AND state != 'archived'` — so a finished run on an archived
issue writes no state change. The method still returns the current row.
Run-row finalization (`run.state`, verdict, summary, comments/context appends)
is NOT guarded — only the issue state write.

**Immediate teardown on idle archive.** In the issue PATCH handler
(`web/api/main.py`), when a PATCH transitions state to `archived` and the
issue has no active run (`latest_run_state` not in `queued`/`running`): if a
worktree exists for the issue (`worktree_exists`), remove it and its branch
via `remove_worktree` (`web/api/worktree.py:83`) and set
`worktree_active = FALSE`. No merge attempt, no comment — output is discarded
by design. Mirror the ordering convention of the existing merge-on-done hook
(main.py:750): publish the row, then run the teardown, returning the final
row.

**Deferred teardown after mid-run archive.** Archiving while a run is in
flight is allowed and must NOT touch the live worktree (the agent is executing
inside it). At run completion, where the engine currently transitions the
issue per verdict (scheduler/agent_runner finalization path), check the
issue's current state first: if `archived`, skip the verdict transition
explicitly (do not rely on the SQL guard alone — log a structured
`archived_terminal` skip line with issue and run ids), remove the worktree and
branch if one exists, and set `worktree_active = FALSE`. Coding bindings run
in the bound checkout: nothing to tear down, agent commits stay — by design.

## Acceptance criteria

- [x] `transition_state` on an archived issue is a no-op for `issue.state` (test: archive, call `transition_state(..., DONE)`, state stays `archived`); non-archived issues transition exactly as before (regression).
- [x] PATCH to `archived` with no active run and an existing worktree removes the worktree directory and its `podium/<binding>/<issue_id>` branch and sets `worktree_active` to false (test against a temp git repo, following `web/api/tests/test_worktree_api.py` fixtures).
- [x] PATCH to `archived` while `latest_run_state` is `queued`/`running` succeeds and leaves the worktree untouched.
- [x] Simulated run completion on an issue archived mid-run: issue stays `archived`, no verdict state transition, worktree and branch removed, `worktree_active` false, structured skip line logged.
- [x] Run-row finalization (run state, verdict, summary) still completes for runs whose issue was archived.
- [x] Merge-on-done behavior (main.py:750) unchanged (regression).

## Verification

```
cd /home/james/symphony && python3 -m pytest
```

## Implementation Notes

Made archived terminal for engine state transitions. `PodiumTrackerAdapter.transition_state` now leaves archived issues archived while still returning the current row. API PATCH to archived tears down idle issue worktrees and branches while deferring active-run teardown. Scheduler run completion now explicitly detects archived issues after run-row finalization, logs `archived_terminal`, removes persistent worktrees, clears `worktree_active`, and skips verdict state resurrection.

Verification passed with `PATH="$PWD/.venv/bin:$HOME/.local/bin:$PATH" python3 -m pytest -q` (622 passed, 1 skipped). Fresh Ralph review returned `PASS`.

## Blocked by

None — #034 completed before this issue started.
