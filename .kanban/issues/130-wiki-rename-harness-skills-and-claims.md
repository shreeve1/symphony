---
id: 130
title: Wiki pass — rename harness skill citations + update removal claims
status: pending
blocked_by: []
parent: null
priority: 0
created: 2026-07-14
---

## What to build

Symphony-local wiki housekeeping for the global harness skill rename + Pi-adapter restoration. Pure text edits in `wiki/`; independently executable (does not require the dotfiles build to have landed, though it logically follows it).

- Rename `personalize-harness → harness-apply` and `audit-ai-readiness → harness-audit` across `wiki/ROUTING.md`, `wiki/index.md`, `wiki/CLAIMS.md`, `wiki/log.md`, and `wiki/analyses/personal-harness-pi-profile.md`. **Exclude `wiki/raw/**`** — it is immutable source capture; its old-name mentions are legitimate history and must not be edited.
- In `wiki/CLAIMS-cold.md` (NOT `CLAIMS.md`) add a supersession/restoration pointer to the new global Pi-adapter (`harness-gates`) design on: **C-0121 (line 23)**, **C-0122 (line 24)**, and **C-0237 at line 194** (the personal-harness-removal entry). Do NOT touch the unrelated duplicate **C-0237 at line 237** (Issue #082 boot reaper). Note the duplicate-C-0237 ID collision inline as a pre-existing issue to dedupe later.
- Append a `wiki/log.md` entry recording the rename + claim update.

Reference (design context): `/home/james/symphony/plans/harness-audit-apply-pairing-pi-gates.md`.

## Acceptance criteria

- [ ] no `personalize-harness` / `audit-ai-readiness` citations remain anywhere in `wiki/` outside `wiki/raw/`
- [ ] `wiki/CLAIMS-cold.md` C-0121, C-0122, and C-0237 (line 194) carry a pointer to the new global-adapter design; the line-237 duplicate is untouched
- [ ] `wiki/log.md` has a new entry for this pass
- [ ] the duplicate-C-0237 ID collision is flagged inline for later dedupe

## Verification

`! grep -RIn 'personalize-harness\|audit-ai-readiness' wiki --exclude-dir=raw && grep -q 'harness-gates\|harness-apply' wiki/CLAIMS-cold.md`

## Blocked by

None in-board — logically follows the dotfiles rename (issue #028, cross-repo, tracked manually), but is independently executable as pure text edits.
