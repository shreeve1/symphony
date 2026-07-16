---
id: 130
title: Wiki pass — rename harness skill citations + update removal claims
status: done
blocked_by: []
parent: null
priority: 0
created: 2026-07-14
updated: 2026-07-15
actor: ralph
---

## What to build

Symphony-local wiki housekeeping for the global harness skill rename + Pi-adapter restoration. Pure text edits in `wiki/`; independently executable (does not require the dotfiles build to have landed, though it logically follows it).

- Rename `personalize-harness → harness-apply` and `audit-ai-readiness → harness-audit` across `wiki/ROUTING.md`, `wiki/index.md`, `wiki/CLAIMS.md`, `wiki/log.md`, and `wiki/analyses/personal-harness-pi-profile.md`. **Exclude `wiki/raw/**`** — it is immutable source capture; its old-name mentions are legitimate history and must not be edited.
- In `wiki/CLAIMS-cold.md` (NOT `CLAIMS.md`) add a supersession/restoration pointer to the new global Pi-adapter (`harness-gates`) design on: **C-0121 (line 23)**, **C-0122 (line 24)**, and **C-0237 at line 194** (the personal-harness-removal entry). Do NOT touch the unrelated duplicate **C-0237 at line 237** (Issue #082 boot reaper). Note the duplicate-C-0237 ID collision inline as a pre-existing issue to dedupe later.
- Append a `wiki/log.md` entry recording the rename + claim update.

Reference (design context): `/home/james/symphony/plans/harness-audit-apply-pairing-pi-gates.md`.

## Acceptance criteria

- [x] no `personalize-harness` / `audit-ai-readiness` citations remain anywhere in `wiki/` outside `wiki/raw/`
- [x] `wiki/CLAIMS-cold.md` C-0121, C-0122, and C-0237 (line 194) carry a pointer to the new global-adapter design; the line-237 duplicate is untouched
- [x] `wiki/log.md` has a new entry for this pass
- [x] the duplicate-C-0237 ID collision is flagged inline for later dedupe

## Implementation Notes

The prior slice (committed as `4c4a71d`) made most of the renames
(`analyses/personal-harness-pi-profile.md`, `analyses/claude-code-harness-profile.md`,
the historical entries in `wiki/log.md`) and committed the new log entry, but
left three loose ends. This slice (commit `702df9e`) closed them:

- **C-0122 (CLAIMS-cold.md line 24)** notes column had no harness-gates
  pointer — added one mirroring the C-0121 / C-0237 (line 194) shape so
  all three removed-Pi-harness rows point at the new global-adapter
  design (`harness-gates` paired with the renamed `harness-apply` skill).
- **C-0237 (line 194)** notes column now flags the duplicate-C-0237 ID
  collision (line 237 — Issue #082 boot reaper) inline as a
  pre-existing issue to dedupe later. Line 237 untouched.
- **`wiki/log.md`** session entry quoted the literal old skill names in
  the task description and verification lines, which broke the issue's
  own `## Verification` command (grep matches the log entry itself).
  Rewrote the task/verification lines to describe the rename pair and
  the verification outcome abstractly so the grep gate stays clean.

**Out of scope (per issue):** `wiki/raw/**` is immutable source — its
old-name mentions are legitimate history and were not edited.

## Verification

`! grep -RIn 'personalize-harness\|audit-ai-readiness' wiki --exclude-dir=raw && grep -q 'harness-gates\|harness-apply' wiki/CLAIMS-cold.md`

## Blocked by

None in-board — logically follows the dotfiles rename (issue #028, cross-repo, tracked manually), but is independently executable as pure text edits.
