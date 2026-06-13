---
id: 049
title: Delta-only resume prompt rendering
status: pending
blocked_by: []
parent: null
priority: 0
created: 2026-06-13
---

## What to build

Add a resume-mode render path to `prompt_renderer.py` that emits the minimal follow-up prompt used when a run resumes an existing agent session. Shared by both the Pi and Claude adapters (cross-cutting, landed once here so 050/051 consume it).

The resume prompt contains ONLY:

- The per-run mechanical wrapper (completion protocol — write this run's result file, then the done/result markers; the existing per-agent wrapper mechanics are reused).
- The single newest `### Operator Reply` block (the delta). Operator-reply gating guarantees exactly one pending reply per parked run.

It explicitly OMITS: issue title/description, the full `comments_md`, the full `context_md`, and the WORKFLOW.md re-inject — all already present in the resumed session. The `flag_operator_replies` elevation collapses: the whole resume prompt IS the operator request.

Symphony still WRITES `comments_md`/`context_md` as today (for UI + the re-feed fallback floor); this slice only changes what is INJECTED on a resume run. WORKFLOW.md edit-mid-issue staleness is accepted (no forced re-inject).

## Acceptance criteria

- [ ] A render function/flag produces a resume prompt = mechanical wrapper + newest operator-reply block only.
- [ ] Resume prompt contains NO issue description, NO full comments blob, NO context blob, NO WORKFLOW.md content.
- [ ] Fresh (non-resume) rendering is unchanged — full prompt still produced for fresh/fallback runs.
- [ ] When multiple operator replies exist historically, only the newest block is included.
- [ ] Mechanical wrapper (result-file/done-marker protocol) is still present in resume mode.

## Verification

`uv run pytest tests/test_prompt_renderer.py tests/test_prompt_renderer_podium.py -q`

## Blocked by

None — can start immediately (parallel with #048).
