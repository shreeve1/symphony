---
id: 120
title: Driver backstop — re-run runnable Verification, override an over-optimistic review pass
status: done
blocked_by: [119]
locks: [scheduler]
priority: 2
created: 2026-06-24
updated: 2026-06-24
actor: ralph
action_reviewed: 2026-06-24
---

## What to build

Per ADR-0023 (tralph parity), do not trust a review run's `done` on faith when the
issue's `## Verification` is a runnable command. After the reviewer emits `done`
(119), the scheduler itself re-runs the verification; a non-zero exit overrides the
pass to `blocked`. This is the highest-risk trust component, sliced separately
because no Python verification extractor exists today (only tralph's shell version),
and it is independently testable against issue-body fixtures.

- Add a verification extractor (Python): parse the issue `description`/body's
  `## Verification` section; return a runnable command only when it is composed of
  backtick-quoted commands joined by connectives (e.g.
  `` `uv run pytest x` and `uv run python -m py_compile y` ``), mirroring tralph's
  `extract_runnable_verification`. Prose verifications (no backtick command) ⇒ return
  nothing ⇒ backstop skipped (the reviewer's agent-mandate from 116 is the only gate).
- In the review-pass terminal (119), before finalizing `done`/land: if the extractor
  yields a command, run it in the issue's worktree cwd. Exit 0 ⇒ proceed with 119's
  pass handling. Non-zero ⇒ override to `blocked`, recording the failing command
  (do NOT land the worktree).
- The backstop runs for BOTH provenances on a review `done` (it gates the pass
  itself, before the auto_land branch).

## Acceptance criteria

- [x] A review `done` whose runnable `## Verification` exits non-zero is overridden to
      `blocked`; the worktree is not landed.
- [x] A review `done` whose verification exits 0 proceeds to 119's provenance-gated
      handling.
- [x] A prose-only `## Verification` (no backtick command) skips the backstop (agent
      mandate only); review `done` is honored.
- [x] The extractor returns nothing for prose and the exact command(s) for the
      backtick-joined form (unit-tested against body fixtures).

## Verification

`uv run pytest tests/test_scheduler.py -q`

## Implementation Notes

Added `_extract_runnable_verification` plus a review-terminal backstop that runs cleanly backticked verification commands before dirty-worktree or auto-land handling. Failed commands finish the Run as blocked, append review output context, block the Issue, and skip landing; prose-only verification falls back to the review agent mandate.
