---
title: "ADR-0026 — Transient terminal failures retry / re-drive instead of blocking"
type: analysis
status: promoted
created: 2026-06-24
updated: 2026-06-25
sources:
  - docs/adr/0026-transient-failure-retry-not-block.md
  - scheduler/__init__.py
  - tests/test_scheduler.py
  - tracker_podium.py
  - web/api/worktree.py
  - worktree_facade.py
  - web/api/schema.py
  - web/api/migrations/versions/0012_retry_verdict.py
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
- **Startup probe timeouts:** after restart onto `0ca14fe`, `verify_pi_support` timed out twice on `pi --print ... ping`, causing systemd restarts before a later probe passed and the scheduler reached steady no-candidate polls.

## Decision summary

- Retry lives in the terminal classifier / auto-land terminal path, not a blocked reconciler sweep.
- Retry uses an allowlist of transient signatures (`server_is_overloaded`, `service_unavailable`, rate-limit/429, 502/503/504, connection reset/error, timeout), not a denylist.
- Timeouts are retryable but capped lower (1) than overload/rate-limit/5xx (2).
- Implement-run transient retry requeues to `todo`; review-run transient retry must re-enter as review using ADR-0024 reland/marker accounting.
- Retry attempts are counted by a visible `### Symphony Retry (transient · N)` comment marker, not a schema column.
- Retry has a modest fixed cooldown (~60s) off the marker timestamp.
- Mid-retry notifications are suppressed; notify only on final block after the cap.
- Auto-land can re-drive when a branch becomes clean/FF-able after rebase or wiki claim renumbering.
- Startup pi probe timeouts should use bounded retry or per-binding fail-soft behavior instead of crashing the scheduler process.
- Claim-ID collision is now part of the unattended landing problem: branch-local "next free C-ID" is not concurrency-safe.

## Implementation status

Partially implemented. Issue #135 landed the auto-land re-drive slice: `_handle_review_terminal_done` retries `_land_review_worktree` exactly once after `asyncio.sleep(2.0)` on any land error, with no error-string narrowing. Retry success proceeds to normal `done` landing; a second failure blocks with the final land error. Tests cover fail-then-success, fail-twice, and the 2s sleep seam [source: scheduler/__init__.py; tests/test_scheduler.py].

Issue #137 landed the review-run terminal retry slice: `_classify_terminal` now catches known-transient nonzero/timeout results for `candidate.review_dispatch`, finishes the Run as `failed` with `verdict="retry"`, appends a `### Symphony Retry (transient · N)` marker plus `### Symphony Reland Pending`, transitions the Issue back to `in_review`, and returns `transient-retry-review`; `tracker_podium.list_candidates` then treats the unconsumed reland marker as another review dispatch only after the retry-marker cooldown expires, preserving the C-0324 `candidate.review_dispatch` provenance gate without immediate retry churn. Exhausting the transient cap blocks and notifies. Podium schema revision `0012_retry_verdict` allows `retry` in `run.verdict` / `issue.latest_verdict`, because the retry Run is projected like other Run completions [source: scheduler/__init__.py; tracker_podium.py; web/api/schema.py; web/api/migrations/versions/0012_retry_verdict.py; tests/test_scheduler.py].

The implement-run terminal-classifier retry and startup probe retry/fail-soft portions remain proposed/unimplemented [source: docs/adr/0026-transient-failure-retry-not-block.md#shippable-in-two-independent-pieces].
