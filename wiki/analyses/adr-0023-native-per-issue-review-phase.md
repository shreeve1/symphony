---
title: "ADR-0023 — Native per-issue review phase for coding bindings, with provenance-gated auto-land"
type: analysis
status: promoted
created: 2026-06-24
updated: 2026-06-24
sources:
  - docs/adr/0023-native-per-issue-review-phase-and-auto-land.md
  - scheduler/__init__.py
  - prompt_renderer.py
  - tests/test_prompt_renderer.py
  - tests/test_scheduler.py
  - agent_runner.py
  - tests/test_agent_runner.py
  - .kanban/issues/116-review-preamble-renderer-constant.md
  - .kanban/issues/120-review-verification-backstop.md
  - web/api/main.py
  - web/api/worktree.py
  - worktree_facade.py
  - web/api/schema.py
  - web/api/migrations/versions/0011_issue_auto_land.py
  - tracker_podium.py
  - "~/.claude/skills/ralph/SKILL.md"
  - "~/.claude/skills/dev-review-pi/SKILL.md"
confidence: high
tags: [adr, review-phase, tralph, ralph, auto-land, worktree, in-review, merge, coding-binding, REVIEW_PREAMBLE, render_review_prompt, implemented, deployed]
---

# ADR-0023 — Native per-issue review phase + provenance-gated auto-land

**Status: accepted + deployed (2026-06-24).** Slices #114–#122 landed and live verification passed on the `symphony` binding. Deploy applied Alembic `0011`, restarted `podium-api`, `podium-web`, and `symphony-host`, and live-smoked slicer auto-land, operator-gated review, backstop override, dirty-worktree blocking, same-worktree review dispatch, and worktree teardown. During the first smoke, Pi RPC dispatch was found to ignore `worktree_active` and run in the base repo; #122 fixed `run_pi_rpc_agent` to create/reuse the issue worktree and use it as cwd, with regression coverage [source: agent_runner.py] [source: tests/test_agent_runner.py]. Trigger model + merge
mechanism corrected after a `dev-review-claude` (opus) pass found the original
"keep it `running` + dispatch inline" and "scheduler calls `_maybe_merge_worktree`"
mechanics unimplementable. Companion to ADR-0021 (P2 conflict-free parallel
dispatch); partially supersedes ADR-0014's operator-merge invariant for the
`auto_land` subset.

## Problem

`tralph` reviews every issue after implementation: a fresh independent reviewer runs
the issue's `## Verification`, fixes in place, or flips `blocked` on an unfixable gap,
with a driver backstop that re-runs runnable verification
[source: ~/.claude/skills/ralph/SKILL.md]. Podium has no equivalent — a coding run
parks `in_review` and waits for an operator to merge, the only path that FF-merges the
worktree into `main` (`web/api/main.py:1141` `patch_issue` → `_maybe_merge_worktree`;
the scheduler never merges, ADR-0014). The human merge is the only review.

## Decision (six parts)

1. **Trigger.** Implement run finishes → issue parks in `in_review` (unchanged). The
   review run is a **second candidate-selection source**: a coding issue in
   `in_review` with no `### Symphony Review` marker is dispatched (Pi) through the
   normal render→run→classify machinery, re-entering the same deterministic
   `worktree_dir`; the marker (written at dispatch) makes the phase idempotent
   across ticks. The original "keep it `running`, dispatch inline" model was
   rejected — candidate selection only picks `STATE_TODO` (`scheduler/__init__.py:1263`),
   so a `running` issue is never re-selected, and inline dispatch would hold the
   `run_cap` semaphore + ADR-0021 lock for the full implement+review span.
2. **Reviewer = service feature, not a skill.** New `REVIEW_PREAMBLE` renderer
   constant in `prompt_renderer.py`, sibling to `INFRA_PREAMBLE` (ADR-0016 pattern),
   forked from `dev-review-pi`'s brief prose but stripped of its interactive
   verify/discuss/apply-with-user steps. Pi-powered; runs the issue's
   `## Verification`, fixes in place, emits `SYMPHONY_RESULT: done|blocked`. Slice #116 landed this foundation as `REVIEW_PREAMBLE` plus `render_review_prompt(issue)`, which renders the preamble + issue body + `OUTPUT_CONTRACT` without skill or `WORKFLOW.md` loading [source: prompt_renderer.py] [source: tests/test_prompt_renderer.py] [source: .kanban/issues/116-review-preamble-renderer-constant.md]. Slice #120 landed the driver backstop: `_handle_review_terminal_done` extracts cleanly backticked `## Verification` commands, runs them in the issue worktree cwd before dirty-worktree/auto-land handling, and blocks without landing on nonzero exit; prose-only verification skips the driver shell gate [source: scheduler/__init__.py] [source: tests/test_scheduler.py] [source: .kanban/issues/120-review-verification-backstop.md].
3. **Scope.** Universal for all `type: coding` bindings; infra excluded (ADR-0020
   `auto_close_on_verified` already covers it).
4. **Pass-terminal is provenance-gated**, behind a **clean-committed-worktree gate**
   (dirty at pass time → `blocked`, never redispatch-to-`todo`). New `issue.auto_land`
   boolean:
   - slicer-authored (`auto_land = true`, set by the 112 `/podium-issues` slicer) →
     `in_review → done` and call a new **process-neutral `land_worktree`** (merge +
     ADR-0021 slice 113 rebase-retry + cleanup, extracted from `_maybe_merge_worktree`
     and re-exported via `worktree_facade`; the scheduler never imports
     `web/api/main.py`). Unattended merge to `main` + a merge notification. Trust
     basis: the slicer guarantees a runnable `## Verification` (same logic ADR-0020
     used for infra).
   - operator-authored (`auto_land = false`, default) → stays `in_review`; operator
     merges via the existing `_maybe_merge_worktree` path (ADR-0014 status quo).
5. **Fail-terminal (both).** Reviewer fixes in place → proceeds; unfixable / dirty /
   backstop-fail → `blocked` (feeds `blocked_reconciler` + ADR-0021 dependency gate).
   **One review per issue — no retry** (a retry would re-review unchanged code).
6. **Schema.** `issue.auto_land BOOLEAN DEFAULT FALSE`, own Alembic migration (after
   ADR-0021's 0010); slice #114 has landed this as `BOOLEAN NOT NULL DEFAULT FALSE` in `0011_issue_auto_land` plus tracker bool read-path coercion (C-0320). `IssueCreate` carrying it and the slicer stamping it remain later slices.

## Why this shape

- **Renderer constant over selectable skill** — the reviewer is a fixed role;
  `INFRA_PREAMBLE` (ADR-0016) is the precedent. `dev-review-pi` is donor text only; its
  interactive, review-only, operator-in-the-loop design is the wrong fit for an
  unattended fix-in-place gate.
- **Review selected from `in_review`, not held inline** — the issue visibly sits in
  `in_review` during review (no new state); a marker-gated second selection source
  triggers the review dispatch on a later tick, so each run takes its own `run_cap`
  slot instead of one issue holding the slot + lock for the full 2x span.
- **Process-neutral `land_worktree`, not a cross-process call** — the scheduler and
  `podium-api` are separate processes; the merge+land core is extracted into
  `web/api/worktree.py` and re-exported via `worktree_facade` so both the API's
  operator-merge wrapper and the scheduler's auto-land path share it without the
  scheduler importing `web/api/main.py` (which would pull in FastAPI and a dirty-tree
  redispatch-to-`todo`).
- **Explicit `auto_land`, not inferred from `external_id`** — provenance decides
  unattended merge-into-`main`, so it must be explicit; overloading the ADR-0015 dedup
  key would silently auto-land anything that sets it.

## Consequences

- Reverses ADR-0014's "coding work always waits for operator merge" — scoped to the
  slicer subset; operator-authored issues keep the human gate.
- ~2x runs per coding issue (implement + review), matching tralph.
- Hard-to-reverse live step (new Alembic migration + `symphony-host` restart) → gated
  MANUAL slice, like ADR-0021's 111. The `symphony` self-binding dogfoods auto-land into
  the live repo — verify on a throwaway slicer-authored batch first.

## Slices (114–122)

114 schema/Alembic 0011 **landed** · 115 create/patch API carries `auto_land` · 116
`REVIEW_PREAMBLE` constant **landed** · 117 extract process-neutral `land_worktree` · 118 review
selection+dispatch (in_review, marker-gated) · 119 review terminal (clean-worktree
gate, provenance-gated pass, fail→blocked) · 120 driver backstop (Python verification
extractor) **landed** · 121 slicer stamps `auto_land=true` · 122 MANUAL deploy. Depends on
ADR-0021 slices 105/108/112/113.

## Status / live verification

- Slices #114–#121 landed via Ralph and passed fresh review.
- Slice #122 deployed the stack to the live repo and services: DB backup written, Alembic upgraded to `0011_issue_auto_land`, frontend rebuilt with `web/frontend/deploy.sh`, `podium-api`/`podium-web`/`symphony-host` restarted, and `symphony-host` came up on code `60c9634`.
- Initial smoke #116 exposed the Pi RPC worktree-cwd gap: the issue recorded a worktree path but `pi_rpc_dispatch` ran from `/home/james/symphony`, so the review backstop blocked. #122 fixed this in `agent_runner.run_pi_rpc_agent`; after restart, journal showed both implement and review runs for #117/#118/#119 dispatching with cwd `/home/james/symphony/worktrees/symphony/<id>`.
- Slicer-authored auto-land smoke #117 passed: implement parked `in_review`, review ran in the same worktree, backstop verification passed, `merge_succeeded` landed branch `podium/symphony/117` to `main`, and `worktree_removed` cleaned the worktree.
- Operator-authored smoke #118 passed: implement + review succeeded, but `auto_land=false` kept the issue `in_review` with reason `review-passed-awaiting-operator-merge` and no merge.
- Dirty-worktree smoke #119 passed: review emitted done and runnable verification passed, but an intentional untracked file left the worktree dirty; terminal handling blocked the issue with “Review auto-land halted: review worktree has uncommitted changes” instead of landing or redispatching to `todo`.
- Existing Issue #102 review after deploy exercised the fail path: a malformed/unreviewable issue was flipped to `blocked` by the review run.
- Throwaway smoke issues #116–#119 were archived after verification; #118/#119 throwaway worktrees were manually removed after recording evidence.
