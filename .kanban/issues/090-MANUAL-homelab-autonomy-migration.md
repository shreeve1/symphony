---
id: 090
title: "MANUAL (not Ralph) — homelab CLAUDE.md safety+autonomy migration + patrol-router repoint (ADR-0016)"
status: pending
blocked_by: [88]
parent: null
priority: 1
created: 2026-06-20
---

## What to build

> ⚠️ **MANUAL OPERATOR ISSUE — DO NOT run via the Ralph loop.** This edits a **different git repo** (`/home/james/homelab`) that the symphony test runner cannot verify, and it precedes a live restart. Ralph must skip it. It is on the board only as the visible rollout step.

The safe, pre-deploy half of ADR-0016's homelab work (group 3, minus the file deletion which lives in #091). Additive only — does NOT delete `~/homelab/WORKFLOW.md` (that waits for the restart in #091). Two pi-review findings reshaped this issue: the patrol-router dependency is a confirmed hard blocker, and the safety section the plan assumed is NOT actually in the live CLAUDE.md.

Source plan: `plans/adr-0016-workflow-md-renderer-constant.md` (tasks 3.1–3.3).

## What to do (manual, in the homelab repo)

- **Repoint the patrol-router renderer (3.1) — CONFIRMED hard prerequisite, not a check.** `~/homelab/automation/homelab-stack/src/homelab_router/prompt_renderer.py:16-17` hard-reads `<homelab root>/WORKFLOW.md` (`_WORKFLOW_DIR = parents[4]`, `_DEFAULT_WORKFLOW_PATH = _WORKFLOW_DIR / "WORKFLOW.md"`) on every call. Give it its own template / bundled default / inline content so it no longer depends on the root file, and update `~/homelab/automation/homelab-stack/tests/test_prompt_renderer.py`. This must be done before the deletion in #091.
- **Safety section is NOT live (3.2) — CONFIRMED.** `~/homelab/CLAUDE.md` has no "Symphony Agent Safety Policy" section (the issue-53 commit `ebdc588` was "local, not pushed" and never reached the live file). The safety enumerations currently live ONLY in `~/homelab/WORKFLOW.md` rules 12/16/17.
- **Migrate BOTH safety and autonomy into `~/homelab/CLAUDE.md` (3.3) — expanded from autonomy-only:**
  - (a) Create the "Symphony Agent Safety Policy" section: baseline prohibitions, the excluded-service list (Symphony, Jellyfin, TrueNAS, Proxmox), and the approval-required categories — sourced from the current `WORKFLOW.md`.
  - (b) Add the autonomy grant (rules 13–17: medium-risk-by-default, capture-state + verify-recovery-in-2–5-min, allowed-mutations list, recovery-failure handling, excluded-service scheduled-only gating, reboot gating), **scoped with "When running unattended under Symphony dispatch, …"** so interactive sessions don't inherit it. It may reference the excluded-service list from (a).
  - Without (a), deleting `WORKFLOW.md` strips ALL safety guidance from the infra agent — a safety regression.
- Commit the homelab CLAUDE.md + patrol-router changes in the homelab repo (base `main`).

## Acceptance criteria

- [ ] Patrol-router renderer repointed off `<homelab>/WORKFLOW.md` and its test updated; `grep -q "WORKFLOW.md" ~/homelab/automation/homelab-stack/src/homelab_router/prompt_renderer.py` no longer resolves to the root file (or the dep is removed).
- [ ] `~/homelab/CLAUDE.md` contains a "Symphony Agent Safety Policy" section with the excluded-service list and approval-required categories.
- [ ] `~/homelab/CLAUDE.md` contains a Symphony-dispatch-scoped autonomy grant (rule 13–17 content); `grep -q "unattended under Symphony dispatch" ~/homelab/CLAUDE.md` succeeds.
- [ ] `~/homelab/WORKFLOW.md` still exists (NOT deleted in this issue).
- [ ] homelab stack tests green after the patrol-router change: `cd ~/homelab/automation/homelab-stack && uv run pytest -q`.

## Verification

Manual operator verification (cross-repo): `grep -q "unattended under Symphony dispatch" /home/james/homelab/CLAUDE.md && grep -qi "excluded service\|Symphony Agent Safety" /home/james/homelab/CLAUDE.md && test -f /home/james/homelab/WORKFLOW.md && echo OK` plus `cd /home/james/homelab/automation/homelab-stack && uv run pytest -q`.

## Blocked by

- Blocked by #88 (renderer must land first so the autonomy content's new home is correct before deploy).
