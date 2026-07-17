---
name: finish-spec
description: "Verify, fix, and close a spec once its child tickets are done. The terminal bookend of to-spec → to-tickets → implement: confirms the slices compose, walks the spec's acceptance criteria against the merged code, fixes only small integration gaps, and closes the spec."
disable-model-invocation: true
---

Verify that a completed spec's feature actually works end-to-end, fix small integration gaps, and close the spec. Use this after every child ticket of a spec has been implemented and closed — not before.

This is a **verification** skill, not an implementation one. It does not build new slices; if it finds a gap too large for a small fix, it files a new ticket rather than growing this run.

## Prerequisites

- The spec's child tickets are all closed. Confirm before starting; if any child is still open, stop and report which — do not verify a half-built feature.

## Process

1. **Fetch the spec.** Read the spec issue's full body and comments (`gh issue view <n> --comments`). Re-read its **Acceptance criteria** / user stories and **Testing Decisions** — those are the checklist.

2. **Run the full suite once, clean.** Backend and frontend, plus typecheck. The child tickets each gated their own slice green; the value here is confirming the slices **compose** — that independently-landed slices don't collide. Fix any failure caused by slice interaction.

3. **Walk the acceptance criteria against the merged code.** For each criterion / user story, confirm the behavior exists — a real end-to-end check, not just "a unit test passed". Use `/code-review` or a fresh reviewer subagent over the combined diff since the spec opened.

4. **Fix only small integration gaps.** Missing wiring between slices, a criterion that no slice quite covered, a stale reference. Keep fixes surgical. If a gap needs a real new slice, **file a new ticket** (via `to-tickets` conventions, `ready-for-agent`) blocked by nothing, and note it on the spec — do not implement it here.

5. **Commit** any fixes to the current branch with a clear message.

6. **Close the spec.** Only when the suite is green and every acceptance criterion is verified:
   - Flip any ADR authored for this spec from `status: proposed` to `status: accepted` (the feature shipped) and commit it.
   - Close the spec issue with a completion note listing the verified child tickets and confirming green suite + acceptance walk (`gh issue close <n> --comment "..."`).

## Rules

- Verify, don't build. New feature work becomes a new ticket, never inline scope growth.
- Close the spec **last**, after green + acceptance walk — closing is the signal the *whole feature* is verified, not that tickets are individually done.
- Do not reopen or modify child tickets; they are done.
