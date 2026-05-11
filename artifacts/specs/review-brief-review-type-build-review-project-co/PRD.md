# Build Review PRD

## Requested Outcome

Review the uncommitted build diff in `/home/james/plane/symphony` for correctness, plan compliance, safety regressions, test completeness, stale runtime references, and risks from untracked files.

## Current State

The working tree contains tracked modifications across the Symphony executor, scheduler, Plane CLI/poller, scripts, and tests. It also contains untracked planning/artifact files and `uv.lock`. The reported validation is:

- `uv run pytest -q`: 249 passed
- `uv run python -m py_compile *.py`: exit 0
- Python-source stale-reference search for `opencode|OPENCODE|OpenCode|CLIPROXY`: no matches

## Ideal State Criteria

- Direct `pi` dispatch replaces OpenCode behavior without losing prompt rendering, Plane state transitions, temporary `plane` PATH shim behavior, or scheduler safety checks.
- Startup-only `pi` verification catches missing binary, unsupported provider/model/auth silent failures, and avoids per-ticket live verification.
- `run_agent` handles blank success output, timeouts, subprocess errors, environment injection, cwd, and output capture safely.
- Scheduler comments, redaction, state transitions, pre-dirty handling, and permission/approval gates remain safe and do not leak secrets.
- Omission of stdout from comments does not remove required marker or workflow signals.
- Included Plane poller dirty changes preserve intended mixed-state pagination behavior.
- Tests cover the relevant executor swap, scheduler, CLI shim, config, startup, and poller behaviors.
- Stale OpenCode/CLIPROXY runtime references are not present outside ignored plan/artifact/cache material.
- Untracked files are understood and do not create release or packaging risk.

## Scope

Review only. Do not edit implementation files unless the user separately requests fixes. Inspect the actual files and uncommitted diff, including the user-requested dirty poller changes.

## Assumptions

- The plan file `plans/symphony-pi-executor-swap.md` is the intended implementation contract.
- The existing dirty poller and scheduler changes are intentional context, not accidental changes to revert.
- Live host environment, systemd, service restarts, and Plane smoke tickets are out of scope.

## Risks

- Passing tests may miss production startup/auth differences for `pi`.
- Scheduler state transitions can regress silently if marker parsing or comment output changes.
- Removing stdout from Plane comments can hide operational signals if those signals are only present in stdout.
- Untracked lockfile or planning artifacts can be accidentally omitted or included.

## Approach

1. Inspect status, diff, plan, and relevant source/tests.
2. Analyze correctness, plan compliance, safety, edge cases, stale references, and test coverage.
3. Attempt mandatory independent Claude review per `dev-review`.
4. Return findings in the exact parser-friendly format requested by the user.

## Verification Plan

- Reconcile findings against source line references in the working tree.
- Compare observed behavior against the plan requirements and user review instructions.
- Note validation already run and identify any residual gaps without performing live operational rollout.
