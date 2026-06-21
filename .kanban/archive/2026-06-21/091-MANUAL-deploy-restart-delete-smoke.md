---
id: 091
title: "MANUAL (not Ralph) — deploy: symphony-restart + delete homelab WORKFLOW.md + live smoke (ADR-0016)"
status: done
blocked_by: [88, 90]
parent: null
priority: 1
created: 2026-06-20
updated: 2026-06-21
---

> **Closed 2026-06-21:** already done in a prior session — `~/homelab/WORKFLOW.md` is deleted; deployed via operator-approved `symphony-host.service` restart onto symphony `7e71b10` (per ADR-0016 status + claim C-0282).

## What to build

> ⚠️ **MANUAL OPERATOR ISSUE — DO NOT run via the Ralph loop.** This mutates live infrastructure (`symphony-host.service` restart) and a different git repo, and requires James's restart gate. Ralph must skip it. It is on the board only as the visible rollout step.

The deploy step for ADR-0016. Ordering is load-bearing: the homelab `WORKFLOW.md` deletion must happen **after** the restart, because the live old-code scheduler reads the file until restarted — deleting first trips `workflow-missing` on live dispatch.

Source plan: `plans/adr-0016-workflow-md-renderer-constant.md` (tasks 3.4, 5.1–5.3).

## What to do (manual)

1. Confirm #088 is merged to symphony `main` and the working tree is clean.
2. Use the `symphony-restart` skill: pre-sanity → **ask James** → restart → verify `symphony_started`, `reconcile_startup_*`, `dispatch_completed` log lines. Now the live scheduler renders infra prompts from `INFRA_PREAMBLE` and ignores `WORKFLOW.md`.
3. **Confirm #090 fully landed before deleting:** the patrol-router renderer is repointed off `<homelab>/WORKFLOW.md` (else the deletion `FileNotFoundError`s the live patrol router — pi review Critical), and the safety policy + autonomy grant are live in `~/homelab/CLAUDE.md` (else deletion strips infra safety — pi review Warning).
4. **Only after a clean restart AND #090 verified:** delete `~/homelab/WORKFLOW.md` and commit in the homelab repo (base `main`).
5. **Live smoke:** dispatch one infra (homelab) issue; from the run log assert the rendered prompt contains the `INFRA_PREAMBLE` (e.g. git-ownership line + narrowed rule 11) and no file-sourced content, and that the agent honors `CLAUDE.md` autonomy (performs an allowed reversible mutation with recovery verification, or correctly blocks on an excluded service).
6. **Post-deletion patrol check:** trigger or await one patrol cycle and confirm the repointed patrol-router renderer still posts issues (no `WORKFLOW.md` FileNotFoundError in the homelab worker logs).

## Acceptance criteria

- [ ] `symphony-host.service` restarted under James approval; post-restart log lines present (`symphony_started` + reconcile + a `dispatch_completed`).
- [ ] #090 confirmed landed (patrol-router repointed; safety+autonomy live in homelab CLAUDE.md) before deletion.
- [ ] `~/homelab/WORKFLOW.md` deleted and committed, **after** the restart (`test ! -f /home/james/homelab/WORKFLOW.md`).
- [ ] One patrol cycle posts cleanly post-deletion (repointed router works; no FileNotFoundError).
- [ ] Live infra dispatch smoke: run-log prompt contains `INFRA_PREAMBLE` markers, no file-sourced WORKFLOW content, autonomy sourced from CLAUDE.md observed.
- [ ] No `workflow-missing` blocks on infra dispatch post-deploy.

## Verification

Manual operator verification: restart log evidence + `test ! -f /home/james/homelab/WORKFLOW.md` + captured live run-log prompt showing the constant. No automated symphony-suite check (live system).

## Blocked by

- Blocked by #88 (renderer code) and #90 (autonomy in CLAUDE.md before the file goes away).
