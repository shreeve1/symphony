# PRD: Round 3 Plan Review

## Requested outcome

Review the latest revised `plans/symphony-pi-executor-swap.md` end-to-end. For
each round-2 finding, determine whether the revision genuinely addresses it,
with special attention to stale reference cleanup, cwd/context parity, startup
verifier insertion order, and live env documentation. Identify any new issues
introduced by the revision.

## Current state

The target is an implementation plan for replacing OpenCode with the local `pi`
CLI in Symphony. Round 2 mostly accepted the round-1 fixes but found remaining
risks around stale OpenCode references, startup probe cwd/context parity,
verifier insertion order before transport construction, and live env
documentation for pi variables.

## Ideal state criteria

- Each prior finding receives a status: `ADDRESSED`, `NOT_ADDRESSED`, or
  `PARTIALLY_ADDRESSED`, with a concise reason.
- Any new revision-caused risks are listed separately in the same severity
  format.
- Evidence is grounded in the current plan and repository files.
- The final response follows the user's exact finding format and ends with
  `END_OF_FINDINGS`.

## Scope

In scope: the revised plan file, the prior round-2 findings, and repository
files/tests needed to verify the plan's claims.

Out of scope: implementing the plan or editing production/test files.

## Assumptions

- The revised plan, not any uncommitted implementation, is the review target.
- Actual repository files remain the feasibility baseline.
- The user's required output format takes precedence over the dev-review
  skill's side-by-side reporting style.

## Risks

- The revision may claim removal while leaving stale references elsewhere.
- New validation commands or tests may be inconsistent with the plan's scope.
- The plan may address symptoms without covering actual execution paths.

## Approach

1. Re-read the full revised plan.
2. Map each round-2 finding to current plan sections and actual code/tests.
3. Verify removal claims with repository searches.
4. Attempt the required Claude cross-check.
5. Produce only validated findings in the requested format.

## Verification plan

- Use `nl`, `rg`, and targeted file reads for exact evidence.
- Check installed `pi --help` only if argument semantics are relevant.
- Confirm final findings against both the plan and actual repo before
  responding.
