---
id: 049
title: Delta-only resume prompt rendering
status: done
blocked_by: []
parent: null
priority: 0
created: 2026-06-13
updated: 2026-06-13
actor: ralph
---

## What to build

Add a resume-mode render path to `prompt_renderer.py` that emits the minimal follow-up prompt used when a run resumes an existing agent session. Shared by both the Pi and Claude adapters (cross-cutting, landed once here so 050/051 consume it).

The resume prompt contains ONLY:

- The per-run mechanical wrapper (completion protocol — write this run's result file, then the done/result markers; the existing per-agent wrapper mechanics are reused).
- The single newest `### Operator Reply` block (the delta). Operator-reply gating guarantees exactly one pending reply per parked run.

It explicitly OMITS: issue title/description, the full `comments_md`, the full `context_md`, and the WORKFLOW.md re-inject — all already present in the resumed session. The `flag_operator_replies` elevation collapses: the whole resume prompt IS the operator request.

**Exception — the skill-invoke directive survives resume.** `preferred_skill` is consume-on-dispatch (CONTEXT.md **Skill**): when an operator reply names a new skill, the resume Run must still invoke it. The skill-invoke prepend (`prompt_renderer.py:236-244`, "First, invoke the `X` skill…") is independent of the comment/context blocks and is **kept on the resume path when `preferred_skill` is set** — it is prepended to the delta prompt exactly as on a fresh run. (The matching `--skill <dir>` load at the resume launch is #050/#051's responsibility.) A skill-less reply resumes plain, as today.

Symphony still WRITES `comments_md`/`context_md` as today (for UI + the re-feed fallback floor); this slice only changes what is INJECTED on a resume run. WORKFLOW.md edit-mid-issue staleness is accepted (no forced re-inject).

## Acceptance criteria

- [x] A render function/flag produces a resume prompt = mechanical wrapper + newest operator-reply block only.
- [x] Resume prompt contains NO issue description, NO full comments blob, NO context blob, NO WORKFLOW.md content.
- [x] Fresh (non-resume) rendering is unchanged — full prompt still produced for fresh/fallback runs.
- [x] When multiple operator replies exist historically, only the newest block is included.
- [x] Mechanical wrapper (result-file/done-marker protocol) is still present in resume mode.
- [x] When the issue has a `preferred_skill` on a resume run, the skill-invoke directive is still prepended to the delta prompt; when it has none, the resume prompt is wrapper + reply block only.

## Verification

`uv run pytest tests/test_prompt_renderer.py tests/test_prompt_renderer_podium.py -q`

## Blocked by

None — can start immediately (parallel with #048).

## Implementation Notes

Added a `resume` render flag in `prompt_renderer.render_prompt()` that returns the shared output contract plus only the newest `### Operator Reply` block. The resume path omits WORKFLOW.md policy, issue body, full comments, and issue context, while preserving the `preferred_skill` invoke directive for Podium resume dispatch. Added focused Podium renderer tests for newest-reply extraction, omission guarantees, skill directive behavior, empty-reply fallback, and fresh render preservation.
