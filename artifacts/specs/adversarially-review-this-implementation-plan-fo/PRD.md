# PRD: Adversarial Plan Review

## Requested outcome

Produce a grounded adversarial review of `plans/symphony-pi-executor-swap.md`
focused on execution risk, feasibility, duplication, missing edge cases,
dependency fit, and test strategy.

## Current state

The repository contains a Python CLI/service for polling Plane work items,
scheduling tickets, launching agents, and notifying on outcomes. The review
target is an implementation plan, not a code change.

## Ideal state criteria

- Every finding is backed by actual repository evidence.
- Findings use the user's required severity format exactly.
- The review does not invent speculative issues.
- The review checks referenced files, existing patterns, dependencies, and
  tests.
- The final line is exactly `END_OF_FINDINGS`.

## Scope

In scope: `plans/symphony-pi-executor-swap.md`, core executor/scheduler/config
files, existing tests, packaging dependencies, and any existing files that
overlap with the plan.

Out of scope: implementing the plan, modifying production code, broad unrelated
architecture cleanup.

## Assumptions

- The plan should be executable by another agent without hidden context.
- Existing code and tests are the source of truth for feasibility.
- User requested final output takes precedence over the dev-review skill's
  side-by-side presentation style.

## Risks

- The plan may reference files or behaviors that do not exist.
- Existing helper scripts may already duplicate proposed work.
- Tests may not cover the most failure-prone integration boundaries.

## Approach

1. Read the plan and identify concrete implementation claims.
2. Inspect current files, tests, and dependencies that the plan touches.
3. Compare proposed steps against actual control flow and code patterns.
4. Attempt the required Claude cross-check if the CLI is available.
5. Return only validated findings in the required format.

## Verification plan

- Use shell reads/searches to verify file paths and dependency declarations.
- Use exact file:line references where possible.
- Re-check findings against the plan and code before finalizing.
