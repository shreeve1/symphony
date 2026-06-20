---
id: 090
title: "MANUAL (not Ralph) — homelab CLAUDE.md autonomy migration + deletion-hazard check (ADR-0016)"
status: pending
blocked_by: [88]
parent: null
priority: 1
created: 2026-06-20
---

## What to build

> ⚠️ **MANUAL OPERATOR ISSUE — DO NOT run via the Ralph loop.** This edits a **different git repo** (`/home/james/homelab`) that the symphony test runner cannot verify, and it precedes a live restart. Ralph must skip it. It is on the board only as the visible rollout step.

The safe, pre-deploy half of ADR-0016's homelab work (group 3, minus the file deletion which lives in #091). Additive only — does NOT delete `~/homelab/WORKFLOW.md` (that waits for the restart in #091).

Source plan: `plans/adr-0016-workflow-md-renderer-constant.md` (tasks 3.1–3.3).

## What to do (manual, in the homelab repo)

- **Deletion-hazard check (3.1):** inspect `~/homelab/automation/homelab-stack/src/homelab_router/prompt_renderer.py` and its test. Confirm whether the patrol router reads `~/homelab/WORKFLOW.md`. If it does, resolve that dependency (own template / inline) so the deletion in #091 is safe. Record the finding in `.kanban/progress.md`.
- **Verify safety section (3.2):** confirm the issue-53 "Symphony Agent Safety Policy" section exists in `~/homelab/CLAUDE.md` (it was not visible in the first ~96 lines on 2026-06-20). Locate it; if genuinely missing, create it.
- **Add the autonomy grant (3.3):** port `WORKFLOW.md` rules 13–17 (medium-risk-by-default, capture-state + verify-recovery-in-2–5-min, the allowed-mutations list, recovery-failure handling, excluded-service scheduled-only gating, reboot gating) into `~/homelab/CLAUDE.md` adjacent to the safety policy, prefixed/scoped with **"When running unattended under Symphony dispatch, …"** so interactive sessions do not inherit it. Reference the already-migrated excluded-service list rather than restating it.
- Commit the homelab CLAUDE.md change in the homelab repo (base `main`).

## Acceptance criteria

- [ ] Patrol-router deletion hazard investigated and finding recorded; if it read `WORKFLOW.md`, dependency resolved.
- [ ] `~/homelab/CLAUDE.md` contains a Symphony-dispatch-scoped autonomy grant (the rule 13–17 content), and `grep -q "unattended under Symphony dispatch" ~/homelab/CLAUDE.md` succeeds.
- [ ] Autonomy grant references (not restates) the excluded-service list already in the safety policy.
- [ ] `~/homelab/WORKFLOW.md` still exists (NOT deleted in this issue).
- [ ] homelab stack tests still green: `cd ~/homelab/automation/homelab-stack && <repo runner> ` (e.g. `uv run pytest -q`).

## Verification

Manual operator verification (cross-repo): `grep -q "unattended under Symphony dispatch" /home/james/homelab/CLAUDE.md && test -f /home/james/homelab/WORKFLOW.md && echo OK` plus the homelab stack test suite.

## Blocked by

- Blocked by #88 (renderer must land first so the autonomy content's new home is correct before deploy).
