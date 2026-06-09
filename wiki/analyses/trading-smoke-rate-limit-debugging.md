---
title: Trading smoke rate-limit debugging
type: analysis
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - wiki/raw/sessions/2026-06-09-trading-smoke-rate-limit.md
  - scheduler.py
  - tests/test_scheduler.py
  - prompt_renderer.py
  - wiki/raw/workflow-trading.md
confidence: high
tags: [trading, smoke-test, plane-429, worktree-retention, conversation-mode, scheduler]
---

# Trading smoke rate-limit debugging

## What happened

A live trading-binding smoke sequence tested the reviewed-landing path: Plane Todo → Running → In Review with a retained Run Worktree. The first useful failure was not agent execution: the agent exited cleanly, then Plane returned 429 during post-agent reconciliation, so the issue stayed Running until recovery logic could retain the worktree for review [source: wiki/raw/sessions/2026-06-09-trading-smoke-rate-limit.md#durable-facts].

## Fixes landed

Three scheduler fixes came out of the session:

1. **Post-agent 429 recovery.** `_DispatchState.pending_review_issue_ids` records clean-exit Runs whose post-agent reconciliation hit `PlaneRateLimitError`; later ticks run `reconcile_pending_review()` before normal polling and move still-Running issues with existing worktrees to In Review [source: scheduler.py#93-114] [source: scheduler.py#919-930] [source: scheduler.py#1495-1670]. Regression coverage: `test_post_agent_rate_limit_retries_review_transition` [source: tests/test_scheduler.py#4315-4375].
2. **Shared Plane 429 cooldown.** `_PLANE_COOLDOWN_UNTIL` is host-level cooldown shared by binding loops, layered with each binding's `_DispatchState.cooldown_until` [source: scheduler.py#57] [source: scheduler.py#117-173]. Regression coverage: `test_plane_rate_limit_cooldown_is_shared_across_states` [source: tests/test_scheduler.py#3964-3990].
3. **Optional label scan removal.** If optional `has-worktree` Role has no UUID and no already resolved ID, Symphony now treats label behavior as unavailable instead of paginating all Plane labels to discover it [source: scheduler.py#850-855] [source: wiki/raw/sessions/2026-06-09-trading-smoke-rate-limit.md#durable-facts]. Regression coverage: `test_has_worktree_label_without_uuid_does_not_scan_plane_labels` [source: tests/test_scheduler.py#529-557].

Verification after these fixes: `python3 -m pytest` passed with 466 tests [source: wiki/raw/sessions/2026-06-09-trading-smoke-rate-limit.md#durable-facts]. Service restart evidence reported `code_sha=c4944be` and retained old issue `6fbfd86a-36b2-4548-9b41-2a80fb66506c` for review [source: wiki/raw/sessions/2026-06-09-trading-smoke-rate-limit.md#durable-facts].

## Remaining smoke-test gap

A new smoke issue `0ab7f64c-3ad4-468d-8c2e-4d408c35f076` dispatched and moved to In Review, but created no `Plans/` file and left no diff; Symphony removed its worktree as clean [source: wiki/raw/sessions/2026-06-09-trading-smoke-rate-limit.md#durable-facts]. This was not a landing bug. It was a mode mismatch: an unlabeled issue resolves/renders as `conversation`, and conversation context tells the agent not to edit files, create commits, or mutate state [source: prompt_renderer.py#141-157].

Trading `WORKFLOW.md` still describes a default `execute` behavior for small routine work and plan artifacts at `Plans/{{issue.identifier}}.md` [source: wiki/raw/workflow-trading.md#17-19]. In practice, unlabeled tickets get the renderer's conversation-mode block after the workflow body. For dirty-worktree landing proof, do not use unlabeled issues until execute semantics are clarified; use `mode:plan` / `mode:build`, or implement explicit execute-mode support.

## Operational lessons

- Retained worktree recovery can now preserve evidence through transient Plane 429 windows, but it cannot prove landing if the agent made no file changes.
- Optional tracker Roles should be treated as disabled when their UUID is absent; dynamic discovery can be too expensive under Plane rate limits.
- Multi-binding Plane polling can amplify 429s. Shared cooldown reduces pressure, but startup and tick sweeps may still need tighter pagination or deferment for nonessential reconcilers.

## Open follow-ups

- Define real execute mode semantics in scheduler/prompt rendering, or update workflow docs to say unlabeled issues are conversation-only.
- Decide whether to create/configure the `has-worktree` label for trading and homelab; until then, optional label behavior remains unavailable.
- Run the final landing proof through a mode that permits file changes, then operator Done landing.
