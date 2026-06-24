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
  - web/api/main.py
  - web/api/worktree.py
  - worktree_facade.py
  - web/api/schema.py
  - "~/.claude/skills/ralph/SKILL.md"
  - "~/.claude/skills/dev-review-pi/SKILL.md"
confidence: high
tags: [adr, review-phase, tralph, ralph, auto-land, worktree, in-review, merge, coding-binding, REVIEW_PREAMBLE, proposed]
---

# ADR-0023 — Native per-issue review phase + provenance-gated auto-land

**Status: proposed (2026-06-24). Not built, not deployed.** Trigger model + merge
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
   `## Verification`, fixes in place, emits `SYMPHONY_RESULT: done|blocked`. Driver
   backstop re-runs runnable verification.
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
   ADR-0021's 0010); `IssueCreate` carries it, the slicer stamps it.

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

114 schema/Alembic 0011 · 115 create/patch API carries `auto_land` · 116
`REVIEW_PREAMBLE` constant · 117 extract process-neutral `land_worktree` · 118 review
selection+dispatch (in_review, marker-gated) · 119 review terminal (clean-worktree
gate, provenance-gated pass, fail→blocked) · 120 driver backstop (Python verification
extractor) · 121 slicer stamps `auto_land=true` · 122 MANUAL deploy. Depends on
ADR-0021 slices 105/108/112/113.

## Status / follow-ups

- Slices written to `.kanban/issues/114-122`. Deploy precondition: ADR-0021 slice 108
  (worktree default-ON) must be live so review-phase issues carry `worktree_active=true`.
- Promote ADR to `accepted` once built + deployed.
