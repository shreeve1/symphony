---
id: 116
title: REVIEW_PREAMBLE renderer constant (unattended fork of dev-review-pi)
status: done
blocked_by: []
locks: [renderer]
priority: 1
created: 2026-06-24
updated: 2026-06-24
actor: ralph
action_reviewed: 2026-06-24
---

## What to build

Per ADR-0023, ship the reviewer's instructions as a renderer constant — the review
phase is a native service feature, NOT a selectable catalog skill. Sibling to
`INFRA_PREAMBLE` (ADR-0016 pattern), in `prompt_renderer.py`.

- Add a `REVIEW_PREAMBLE` constant in `prompt_renderer.py` (sibling to
  `INFRA_PREAMBLE` / `OUTPUT_CONTRACT`). Fork the review-brief prose from the
  `dev-review-pi` skill (`~/.claude/skills/dev-review-pi/SKILL.md`) but **strip every
  interactive step**: no "verify scope with user", no "discuss findings", no "apply
  only what the user agrees on" — Symphony runs unattended.
- The preamble instructs the reviewer (a fresh agent run, scoped to the issue's
  worktree-branch diff vs base) to:
  1. Gather context and form an independent judgment of the implemented work.
  2. **Run the issue's `## Verification` command exactly as written**; it may only
     conclude success if it exits 0.
  3. **Fix in place** (edit/test/commit in the worktree) when it can close a gap.
  4. Emit exactly one terminal `SYMPHONY_RESULT: done|blocked` marker — `done` when
     verification passes (after any in-place fix), `blocked` for an unfixable gap.
- Expose a render path for the review phase: `render_prompt` (or a sibling entry the
  scheduler calls in 117) emits `REVIEW_PREAMBLE` + the issue body/verification +
  the existing `OUTPUT_CONTRACT`, the same way infra dispatch emits `INFRA_PREAMBLE`.
  No `WORKFLOW.md`/skill load on this path.
- This slice is the constant + render wiring only; the scheduler dispatch that
  consumes it is 117.

## Acceptance criteria

- [x] `REVIEW_PREAMBLE` exists in `prompt_renderer.py`; no interactive/operator-in-
      the-loop instructions remain (review runs unattended).
- [x] The preamble mandates running the issue's `## Verification` and emitting one
      `SYMPHONY_RESULT: done|blocked` marker; permits in-place fix.
- [x] A review-phase render produces `REVIEW_PREAMBLE` + verification + the output
      contract, with no skill/WORKFLOW.md load.

## Verification

`uv run pytest tests/test_prompt_renderer.py -q`
and `uv run python -m py_compile prompt_renderer.py`

## Implementation Notes

Added `REVIEW_PREAMBLE` plus `render_review_prompt(issue)` so review dispatch can render the review contract, issue body, and centralized output contract without skill or WORKFLOW loading. Covered the unattended review path in `tests/test_prompt_renderer.py`.
