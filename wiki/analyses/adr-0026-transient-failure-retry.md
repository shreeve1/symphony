---
title: "ADR-0026 — Transient terminal failures retry / re-drive instead of blocking"
type: analysis
status: promoted
created: 2026-06-24
updated: 2026-07-20
sources:
  - docs/adr/0026-transient-failure-retry-not-block.md
  - wiki/raw/sessions/2026-07-20-podium-startup-model-probe-decoupling.md
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
- Startup pi probe timeouts must not crash the scheduler process. As amended on 2026-07-20, Podium does not probe its catalog-default provider/model at startup; model availability is scoped to per-Issue dispatch. Local non-Podium Pi bindings retain bounded retry/fail-soft probing.
- Claim-ID collision is now part of the unattended landing problem: branch-local "next free C-ID" is not concurrency-safe.

## Implementation status

Fully implemented and live as of restart to `code_sha=fb799be` (2026-06-25 05:09 UTC). All five Podium slices (#133–#137) are `done` [source: wiki/raw/sessions/2026-06-25-adr-0026-land-and-model-switch.md].

- **#135 auto-land re-drive:** `_handle_review_terminal_done` retries `_land_review_worktree` exactly once after `asyncio.sleep(2.0)` on any land error, with no error-string narrowing. Retry success proceeds to normal `done` landing; a second failure blocks with the final land error. Tests cover fail-then-success, fail-twice, and the 2s sleep seam [source: scheduler/__init__.py; tests/test_scheduler.py].
- **#137 review-run retry:** `_classify_terminal` catches known-transient nonzero/timeout results for `candidate.review_dispatch`, finishes the Run as `failed` with `verdict="retry"`, appends a `### Symphony Retry (transient · N)` marker plus `### Symphony Reland Pending`, transitions the Issue back to `in_review`, and returns `transient-retry-review`; `tracker_podium.list_candidates` re-dispatches as review only after the retry-marker cooldown expires, preserving the C-0324 provenance gate. Cap exhaustion blocks and notifies [source: scheduler/__init__.py; tracker_podium.py; tests/test_scheduler.py].
- **#136 implement-run retry:** `_classify_terminal` (non-review path) finishes the Run as `failed`/`verdict="retry"`, appends a retry marker, and transitions the Issue to `todo` under cap + cooldown; `_select_run_tick_candidate` additionally suppresses re-selection while the cooldown is unexpired. Non-transient failures and cap exhaustion fall through to the existing block + notify path [source: scheduler/__init__.py `_maybe_retry_transient_implement`, `_retry_comments_text`; tests/test_scheduler.py].
- **#134 startup-probe fail-soft, amended 2026-07-20:** historically, `_probe_binding` retried `verify_pi_support` and skipped one binding on exhaustion. A live `pi-duo/Duo` quota cooldown then skipped every local Podium binding even though queued Issues explicitly selected healthy `gpt-5.6-sol`. Podium bindings now bypass this provider/model startup probe; `verify_pi_rpc_support` still checks model-independent RPC capability globally, and the existing per-Issue dispatch gate resolves and validates each selected model. The bounded startup provider/model probe remains only for local non-Podium Pi bindings (C-0395) [source: main.py; tests/test_main.py; tests/test_agent_runner.py; wiki/raw/sessions/2026-07-20-podium-startup-model-probe-decoupling.md].
- Podium schema revision `0012_retry_verdict` allows `retry` in `run.verdict` / `issue.latest_verdict` [source: web/api/schema.py; web/api/migrations/versions/0012_retry_verdict.py].

## Allowlist expansion (2026-06-25)

The original allowlist (`server_is_overloaded`, `service_unavailable`, rate-limit/429, 502/503/504, connection reset/error) did not match observed Codex provider failures, which surface as `exit_code=1, timed_out=false` with stderr like `Codex SSE response headers timed out after 20000ms` or bare `terminated`. These blocked even after the retry machinery landed. The allowlist was expanded to add `timed out`, `timeout`, `\bsse\b`, and `\bterminated\b` (commit `a35f327`) [source: scheduler/transient_retry.py; tests/test_transient_retry.py; run #409 stderr]. A remaining gap: ADR-0026's retry handles terminated agents, not frozen/stalled ones (see stall-detection follow-up).

## Follow-ups resolved by grill (2026-06-25)

The three open follow-ups left after ADR-0026 shipped were grilled and resolved into three accepted ADRs:

- **Stall watchdog (C-0336) → [ADR-0027](../../docs/adr/0027-agent-stall-watchdog.md):** kill a frozen agent after 15min of session-jsonl silence; new stall retry class distinct from the transient allowlist (a frozen agent has no stderr signature). See C-0337.
- **Parallel-slice land friction (C-0335) → [ADR-0028](../../docs/adr/0028-slice-runs-exempt-from-wiki-obligation.md)** (wiki-churn: slices exempt from the wiki obligation; one consolidated post-land pass) **+ slicer `locks: [migrations]` convention** (duplicate-migration: reuse existing dispatch lock enforcement). See C-0338.
- **Contract gate drift + markers.py → [ADR-0029](../../docs/adr/0029-contract-gate-frozen-corpus.md):** freeze the scoring corpus to a checked-in fixture (drift was DB hygiene, not parser regression); the markers.py `retry` gap is rejected by design (retry is machine-set, never agent-declared). See C-0339.
