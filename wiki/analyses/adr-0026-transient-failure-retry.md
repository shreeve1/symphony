---
title: "ADR-0026 — Transient terminal failures retry / re-drive instead of blocking"
type: analysis
status: promoted
created: 2026-06-24
updated: 2026-06-24
sources:
  - docs/adr/0026-transient-failure-retry-not-block.md
  - scheduler/__init__.py
  - tracker_podium.py
  - web/api/worktree.py
  - worktree_facade.py
  - wiki/raw/sessions/2026-06-24-adr-0024-babysitting-roadblocks.md
confidence: high
tags: [adr, transient-failure, retry, auto-land, review-retry, blocked, Codex, server_is_overloaded, claim-id-collision]
---

# ADR-0026 — Transient terminal failures retry / re-drive instead of blocking

ADR-0026 is proposed after the ADR-0024 batch exposed that the dispatch loop still requires operator babysitting for failures that are not product defects. The core decision is to retry/re-drive known-transient terminal failures at the point of classification, instead of immediately parking the Issue in `blocked`.

## Observed roadblocks

- **Provider overload / 503:** Issues #128, #129, and #131 blocked after Codex returned `server_is_overloaded`. #128 failed during implementation and needed requeue to `todo`; #129/#131 failed during review and needed the review marker stripped/neutralized so review could re-dispatch.
- **Auto-land re-drive:** #130 and #131 had passing reviews but blocked during auto-land after `main` advanced. Rebase/renumbering made the branches landable, but nothing re-drove `land_worktree`; a human had to call it and flip the Issue state.
- **Concurrent wiki claim IDs:** #131 collided with an unrelated C-0327 claim from a frontend fix. The branch had to be rebased with #131's empty-diff claim renumbered to C-0328 before landing.

## Decision summary

- Retry lives in the terminal classifier / auto-land terminal path, not a blocked reconciler sweep.
- Retry uses an allowlist of transient signatures (`server_is_overloaded`, `service_unavailable`, rate-limit/429, 502/503/504, connection reset/error, timeout), not a denylist.
- Timeouts are retryable but capped lower (1) than overload/rate-limit/5xx (2).
- Implement-run transient retry requeues to `todo`; review-run transient retry must re-enter as review using ADR-0024 reland/marker accounting.
- Retry attempts are counted by a visible `### Symphony Retry (transient · N)` comment marker, not a schema column.
- Retry has a modest fixed cooldown (~60s) off the marker timestamp.
- Mid-retry notifications are suppressed; notify only on final block after the cap.
- Auto-land can re-drive when a branch becomes clean/FF-able after rebase or wiki claim renumbering.
- Claim-ID collision is now part of the unattended landing problem: branch-local "next free C-ID" is not concurrency-safe.

## Status

Proposed only. No code implements ADR-0026 yet. ADR-0024 slices #128-#132 are landed, but the observed roadblocks were recovered manually.
