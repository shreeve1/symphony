---
id: 091
title: "MANUAL (not Ralph) — deploy: symphony-restart + delete homelab WORKFLOW.md + live smoke (ADR-0016)"
status: pending
blocked_by: [88, 90]
parent: null
priority: 1
created: 2026-06-20
---

## What to build

> ⚠️ **MANUAL OPERATOR ISSUE — DO NOT run via the Ralph loop.** This mutates live infrastructure (`symphony-host.service` restart) and a different git repo, and requires James's restart gate. Ralph must skip it. It is on the board only as the visible rollout step.

The deploy step for ADR-0016. Ordering is load-bearing: the homelab `WORKFLOW.md` deletion must happen **after** the restart, because the live old-code scheduler reads the file until restarted — deleting first trips `workflow-missing` on live dispatch.

Source plan: `plans/adr-0016-workflow-md-renderer-constant.md` (tasks 3.4, 5.1–5.3).

## What to do (manual)

1. Confirm #088 is merged to symphony `main` and the working tree is clean.
2. Use the `symphony-restart` skill: pre-sanity → **ask James** → restart → verify `symphony_started`, `reconcile_startup_*`, `dispatch_completed` log lines. Now the live scheduler renders infra prompts from `INFRA_PREAMBLE` and ignores `WORKFLOW.md`.
3. **Only after a clean restart:** delete `~/homelab/WORKFLOW.md` and commit in the homelab repo (base `main`).
4. **Live smoke:** dispatch one infra (homelab) issue; from the run log assert the rendered prompt contains the `INFRA_PREAMBLE` (e.g. git-ownership line + narrowed rule 11) and no file-sourced content, and that the agent honors `CLAUDE.md` autonomy (performs an allowed reversible mutation with recovery verification, or correctly blocks on an excluded service).

## Acceptance criteria

- [ ] `symphony-host.service` restarted under James approval; post-restart log lines present (`symphony_started` + reconcile + a `dispatch_completed`).
- [ ] `~/homelab/WORKFLOW.md` deleted and committed, **after** the restart (`test ! -f /home/james/homelab/WORKFLOW.md`).
- [ ] Live infra dispatch smoke: run-log prompt contains `INFRA_PREAMBLE` markers, no file-sourced WORKFLOW content, autonomy sourced from CLAUDE.md observed.
- [ ] No `workflow-missing` blocks on infra dispatch post-deploy.

## Verification

Manual operator verification: restart log evidence + `test ! -f /home/james/homelab/WORKFLOW.md` + captured live run-log prompt showing the constant. No automated symphony-suite check (live system).

## Blocked by

- Blocked by #88 (renderer code) and #90 (autonomy in CLAUDE.md before the file goes away).
