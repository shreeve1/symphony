---
id: 092
title: "MANUAL (not Ralph) — ADR-0016 + wiki: mark implemented (ADR-0016)"
status: done
blocked_by: [91]
parent: null
priority: 2
created: 2026-06-20
updated: 2026-06-21
---

> **Closed 2026-06-21:** mostly done in a prior session (ADR-0016 status flipped to "landed"; CLAIMS C-0276/0277/0278 marked implemented; `wiki/log.md` entry present). Final straggler closed this session: `wiki/entities/workflow-homelab.md` was still marked "decision only, NOT yet implemented" — updated to reflect the file is deleted and the prompt renders from `INFRA_PREAMBLE`.

## What to build

> ⚠️ **MANUAL OPERATOR ISSUE — DO NOT run via the Ralph loop.** This flips status records to "implemented", which is only TRUE once the deploy in #091 is verified live. Running it earlier would record a false state. It also needs wiki/claim judgment (`/wiki-update`). Ralph must skip it.

Close the documentation loop for ADR-0016 once the deploy (#091) is confirmed live.

Source plan: `plans/adr-0016-workflow-md-renderer-constant.md` (task 5.4).

## What to do (manual)

- Flip `docs/adr/0016-workflow-md-retired-renderer-constant.md` status note from "design pass; implementation not started" to landed/implemented.
- Run `/wiki-update`: move claims **C-0276 / C-0277 / C-0278** from "decision only / not yet migrated" to implemented; update `wiki/entities/workflow-homelab.md` (file now deleted, not "slated for deletion"); append a `wiki/log.md` entry; refresh `wiki/index.md` rows.
- Optionally mark `CONTEXT.md`'s Workflow term as no longer "implementation pending".

## Acceptance criteria

- [ ] ADR-0016 status reflects landed/implemented.
- [ ] C-0276/C-0277/C-0278 notes updated to implemented in `wiki/CLAIMS.md`.
- [ ] `wiki/entities/workflow-homelab.md` reflects the file is deleted (not pending).
- [ ] `wiki/log.md` has a closing entry; `wiki/index.md` rows refreshed.

## Verification

Manual: `grep -i "implement" docs/adr/0016-workflow-md-retired-renderer-constant.md` and review of the updated CLAIMS/index/log rows. Doc-only; no code test.

## Blocked by

- Blocked by #91 (status may only be flipped to implemented after the live deploy is verified).
