---
id: 008
title: WORKFLOW.md mandatory renderer
status: done
blocked_by: [7]
parent: null
priority: 0
created: 2026-06-04
updated: 2026-06-05
actor: ralph
---

## What to build

Make the per-repo `WORKFLOW.md` the whole prompt policy for a binding's repo.
The renderer reads `WORKFLOW.md` from the bound repo root on each dispatch and
stays pure mechanism (variable substitution, issue/comment escaping, schedule
block) — the agent self-selects relevance from the issue's labels. A binding
whose repo has no readable `WORKFLOW.md` is a hard config error: Symphony refuses
to dispatch, skips the issue, and posts a blocked comment naming the missing
file. There is no built-in fallback policy (the homelab-era label-selected prompt
fragments are dropped).

See the **Workflow** and **Mode** glossary entries in `CONTEXT.md`.

## Acceptance criteria

- [x] The renderer composes the prompt from the bound repo's `WORKFLOW.md` plus engine-supplied variables.
- [x] Missing/unreadable `WORKFLOW.md` ⇒ no dispatch, issue skipped, and a blocked comment posted naming the file.
- [x] The renderer performs no label-based prompt-fragment selection (pure mechanism).
- [x] Mode is exposed to the renderer as a variable; engine still owns the side-effect backstop.
- [x] Suite green, covering both the happy path and the missing-file refusal.

## Verification

`uv run pytest`

## Blocked by

- Blocked by #7

## Implementation Notes

- `main.py` passes each binding's repo root to the renderer so prompts are built from that repo's `WORKFLOW.md`.
- `prompt_renderer.py` now only loads `WORKFLOW.md`, substitutes issue variables, escapes issue/comment content, and appends schedule context; legacy mode directives and domain overlays were removed.
- `scheduler.py` renders before dispatch and blocks the issue with a comment naming `WORKFLOW.md` when the workflow file is missing or unreadable.
- Added prompt-renderer and scheduler coverage for happy path, missing workflow refusal, mode variables, and absence of label-selected fragments.
