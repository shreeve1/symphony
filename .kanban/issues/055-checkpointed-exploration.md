---
id: 055
title: Checkpointed exploration mode
status: done
blocked_by: [050, 051, 052]
parent: null
priority: 0
created: 2026-06-13
updated: 2026-06-14
actor: ralph
---

## What to build

A prompt-policy pattern (not engine plumbing) that makes exploratory issues proceed in reviewable increments instead of one opaque unattended lunge: the agent does one bounded step, then parks for review (via Question Park, #052), and resumes on the operator's reply (#050/#051).

- Add an exploration Skill (and/or WORKFLOW-author guidance) instructing the agent to scope work into a single bounded step per Run, summarize, and park rather than running to completion.
- The prompt renderer emits the checkpoint directive when that exploration skill is the issue's preferred skill (reusing the existing Skill→prompt-directive mechanism).
- No new state machine: leans entirely on Session Resume + Question Park already landed.

## Acceptance criteria

- [x] An exploration Skill exists in the catalog with a SKILL.md describing bounded-step-then-park.
- [x] When that skill is selected, the rendered prompt contains the checkpoint/bounded-step directive; when not selected, it does not.
- [x] The directive instructs a Question-Park-style park after each bounded step (no completion claimed until the operator signals done).
- [x] Documented in the WORKFLOW-author guidance so future bindings can adopt it.

## Verification

`uv run pytest tests/test_prompt_renderer*.py tests/skills/ -q`

## Blocked by

- Blocked by #050, #051, #052

## Implementation Notes

Added the repo-local `checkpointed-exploration` Skill, a prompt-renderer directive emitted only when that Skill is selected, and workflow-author guidance for documenting bounded exploration on future bindings. Covered catalog scanning, prompt emission/omission, resume prompt preservation, and workflow-author documentation with tests.
