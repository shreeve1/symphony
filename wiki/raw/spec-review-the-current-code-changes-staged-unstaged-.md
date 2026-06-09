# PRD: Review Current Code Changes

## Requested outcome
Review all current staged, unstaged, and untracked changes in this repository and return prioritized, actionable findings in the required JSON review format.

## Current state
The working tree contains modifications to core Python modules and tests plus untracked planning/artifact files and `uv.lock`. The exact behavioral intent must be inferred from the diff and surrounding code.

## Ideal state criteria
- Identify only discrete bugs/regressions introduced by the current changes that the author would likely fix.
- Ground every finding in an exact changed line with the shortest useful range.
- Prioritize findings by impact and confidence.
- Return no findings if the patch appears correct.
- Do not propose fixes or alter production code during review.

## Scope
In scope: staged, unstaged, and untracked files present before this review artifact was created. Out of scope: unrelated pre-existing issues and this PRD artifact itself.

## Assumptions
- The user wants a standard inline-review JSON response, not code edits.
- Tests may be inspected but not necessarily executed unless needed to validate a suspected issue.
- Untracked planning files may be reviewed when relevant, but review comments should focus on code/config/test changes.

## Risks
- Creating this PRD adds an untracked file; it must be excluded from review findings.
- Some behavioral intent may be unclear from diff alone; findings must avoid speculation.
- Running tests could be slow or environment-dependent.

## Approach
1. Inspect git status and diffs, including untracked files existing before this PRD.
2. Read affected source and tests to understand behavior and expected contracts.
3. Analyze for correctness, security, performance, maintainability, and test regressions.
4. Attempt the required independent Claude review pass if available.
5. Produce findings in the required JSON schema.

## Verification plan
- Use git diff/stat and targeted file reads to verify changed lines and line numbers.
- Optionally run focused tests or static checks if needed for confidence.
- Review final findings against the criteria and output schema before responding.
