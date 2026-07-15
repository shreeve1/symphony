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

- Rename references to the two **current** skills — `personalize-harness → harness-apply` and `audit-ai-readiness → harness-audit` — across `wiki/ROUTING.md`, `wiki/index.md`, `wiki/CLAIMS.md`, `wiki/log.md`, and `wiki/analyses/personal-harness-pi-profile.md`. **Exclude `wiki/raw/**`** (immutable source capture — its old-name mentions are legitimate history).
- **CRITICAL scoping — one rule: rename `personalize-harness` ONLY where it is NOT immediately followed by `-pi`.** That single rule is correct for every case:
  - DO rename bare skill refs AND the skill's own moved path citations, e.g. `~/.claude/skills/personalize-harness/SKILL.md` → `~/.claude/skills/harness-apply/SKILL.md`, and the ROUTING keyword `personalize-harness` → `harness-apply` (the skill moved).
  - Do NOT touch `personalize-harness-pi` (a DIFFERENT, retired skill) anywhere — it appears ~15× including inside immutable artifact filenames like `.rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md`. Renaming those would break real citations.
  - Unrelated, leave untouched: the removed extension `.pi/extensions/personal-harness.ts` and files named `personal-harness-pi-*` (spelled `personal-harness`, no `-ize`).
- The `audit-ai-readiness → harness-audit` half is effectively a **no-op**: there are currently 0 `audit-ai-readiness` references in the mutable wiki (all live in `raw/`). Apply it anyway for safety, but expect nothing to change.
- Scope note: this issue only RENAMES citations and adds the claim-status pointer. It does NOT reconcile now-stale behavioral detail — e.g. C-0130 describes the old `pre-git-checks.sh` running `uv run pytest -q`, which issue 029 changes; that behavioral reconciliation is a later `/wiki-update`, not this pass.
- In `wiki/CLAIMS-cold.md` (NOT `CLAIMS.md`) add a supersession/restoration pointer to the new global Pi-adapter (`harness-gates`) design on: **C-0121 (line 23)**, **C-0122 (line 24)**, and **C-0237 at line 194** (the personal-harness-removal entry). Do NOT touch the unrelated duplicate **C-0237 at line 237** (Issue #082 boot reaper). Note the duplicate-C-0237 ID collision inline as a pre-existing issue to dedupe later.
- Append a `wiki/log.md` entry recording the rename + claim update.

Reference (design context): `/home/james/symphony/plans/harness-audit-apply-pairing-pi-gates.md`.

## Acceptance criteria

- [ ] no bare-skill `personalize-harness` (not `-pi`, not a filename) or `audit-ai-readiness` citations remain in `wiki/` outside `wiki/raw/`; all `personalize-harness-pi` occurrences and citation filenames are preserved unchanged
- [ ] `wiki/CLAIMS-cold.md` C-0121, C-0122, and C-0237 (line 194) carry a pointer to the new global-adapter design; the line-237 duplicate is untouched
- [ ] `wiki/log.md` has a new entry for this pass
- [ ] the duplicate-C-0237 ID collision is flagged inline for later dedupe

## Verification

`test -z "$(grep -RIn 'personalize-harness' wiki --exclude-dir=raw | grep -v 'personalize-harness-pi')" && ! grep -RIn 'audit-ai-readiness' wiki --exclude-dir=raw && grep -q 'harness-gates\|harness-apply' wiki/CLAIMS-cold.md`

## Blocked by

None in-board — logically follows the dotfiles rename (issue #028, cross-repo, tracked manually), but is independently executable as pure text edits.
