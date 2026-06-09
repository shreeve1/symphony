---
title: Scheduler loop (scheduler.py)
type: concept
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - scheduler.py
confidence: medium
tags: [scheduler, dispatch-loop, semaphore, in-flight, rate-limit, claim, landing, reconcile]
---

# Scheduler loop (`scheduler.py`)

The engine heart. 2633 LOC, 59 top-level def/class. This page documents the durable constants, concurrency model, and high-level async function shape. It does NOT capture every code path — extract claims on demand when specific questions surface.

## Key constants

### Identity and claim

| Constant | Value | Purpose |
|---|---|---|
| `CLAIM_PREFIX` | `"Symphony claimed at "` | first token of the claim comment body; parsed by `_claimed_at()` |
| `_CODE_SHA` | resolved at import | appended after the claim timestamp as `code_sha=<sha>`; backwards-compatible because `_claimed_at` splits on `CLAIM_PREFIX` and takes the first whitespace token |
| `HAS_WORKTREE_LABEL_NAME` | `"has-worktree"` | optional Role label marking issues with a live or retained Run Worktree |

### Report / comment shaping

| Constant | Value | Purpose |
|---|---|---|
| `REPORT_MAX_BYTES` | `2048` | total size cap on Plane comments |
| `STDERR_SUMMARY_MAX_LINES` | `8` | hard cap when summarising stderr into a comment |
| `STDERR_SUMMARY_MAX_CHARS` | `900` | char cap on same |
| `PREVIOUS_COMMENT_MAX_CHARS` | `1500` | per-comment cap when embedding earlier comments |
| `PREVIOUS_COMMENT_TAIL_CHARS` | `500` | tail kept when truncating |
| `SUMMARY_MAX_CHARS` | `500` | hoisted from `SYMPHONY_SUMMARY:` marker into completion comment (matches homelab WORKFLOW rule 16) |

### Pagination

| Constant | Value |
|---|---|
| `SCHEDULED_RELEASE_PAGE_SIZE` | `50` |
| `SCHEDULED_RELEASE_MAX_PAGES_PER_TICK` | `3` |
| `DONE_LANDING_PAGE_SIZE` | `50` |
| `DONE_LANDING_MAX_PAGES_PER_TICK` | `3` |

### Rate-limit cooldown

| Constant | Value | Purpose |
|---|---|---|
| `RATE_LIMIT_BASE_COOLDOWN_S` | `30.0` | base sleep on first Plane 429 |
| `RATE_LIMIT_MAX_COOLDOWN_S` | `300.0` | upper bound on backoff |
| `RATE_LIMIT_JITTER_FRACTION` | `0.2` | ±20% jitter |

### Scheduled-label maintenance window

| Constant | Value |
|---|---|
| `SCHEDULED_LABEL_WINDOW_TZ` | `ZoneInfo("America/Los_Angeles")` |
| `SCHEDULED_LABEL_WINDOW_START_HOUR` | `0` |
| `SCHEDULED_LABEL_WINDOW_END_HOUR` | `6` |
| `SCHEDULED_LABEL_DEFAULT_REASON` | `"scheduled label maintenance window"` |
| `SCHEDULED_LABEL_DEFAULT_SOURCE` | `"scheduled label maintenance window (12am-6am PT)"` |

These implement the C-0012 fallback: a Plane `scheduled` label without a `Symphony-Schedule:` comment defaults to the next 12am-6am PT window.

### Dirty-base landing approval protocol

| Constant | Value | Purpose |
|---|---|---|
| `DIRTY_BASE_APPROVAL_COMMAND` | `"Symphony-Landing: auto-commit-base"` | operator-typed comment authorising auto-commit of dirty base checkout |
| `DIRTY_BASE_TOKEN_PREFIX` | `"Dirty-Base-Token:"` | per-instance nonce that must match in the approval comment |
| `DIRTY_BASE_STATUS_MAX_LINES` | `20` | cap on `git status` output included in the audit block |

### Stale-running grace

| Constant | Value | Purpose |
|---|---|---|
| `INTERRUPTED_RUNNING_REVIEW_GRACE_S` | `60.0` | grace before reclaiming a Running issue with no in-flight local Run but an existing Run Worktree |

## Concurrency model

### Per-binding `_DispatchState`

Each `run_loop` creates a per-binding `_DispatchState` with its own `asyncio.Semaphore` capping live Runs. The semaphore replaces the legacy single global flock (per [ADR-0003](../analyses/adr-0003-worktree-per-run.md)) [source: scheduler.py#48-57, 94-115].

### Module-level fallback (legacy compat)

`_RUN_SEMAPHORE`, `_POLL_INTERVAL_S`, `_IN_FLIGHT_ISSUE_IDS`, `_IN_FLIGHT_LOCK`, `_PLANE_COOLDOWN_UNTIL` are retained for backward compat with tests that call `run_tick` / `_dispatch_one` directly via `_fallback_dispatch_state()`. Production path uses the per-binding `_DispatchState` exclusively.

### Rate-limit state

`_record_rate_limit`, `_cooldown_remaining_s`, `_clear_rate_limit` manage both per-binding cooldown (`_DispatchState.cooldown_until`) and shared host cooldown (`_PLANE_COOLDOWN_UNTIL`). One binding's Plane 429 now suppresses other binding dispatch probes until the shared cooldown clears, reducing multi-binding 429 amplification. Bounds: `[RATE_LIMIT_BASE_COOLDOWN_S, RATE_LIMIT_MAX_COOLDOWN_S]`, with jitter also applied to `Retry-After` delays [source: scheduler.py#57] [source: scheduler.py#117-173] [source: wiki/raw/sessions/2026-06-09-trading-smoke-rate-limit.md#durable-facts].

## Verdict-marker parsing

| Function | Purpose |
|---|---|
| `_parse_result_marker(stdout)` | scan for `SYMPHONY_RESULT: done\|review\|blocked`; last occurrence wins, case-insensitive prefix, unknown values ignored |
| `_parse_summary_marker(*streams)` | scan stdout (and stderr) for `SYMPHONY_SUMMARY: ...`; capped at `SUMMARY_MAX_CHARS`, ANSI-stripped, single-line |
| `_hit_permission_gate(stdout, stderr)` | detect pi/agent permission-denied marker text |
| `_hit_approval_gate(stdout, stderr)` | detect approval-required gate |

[source: scheduler.py#193-256]

## High-level async surface

Top-level coroutines (selected) [source: scheduler.py#687-2502]:

| Coroutine | Role |
|---|---|
| `run_loop` | per-binding scheduler driver; spawns `_dispatch_one` while holding the semaphore |
| `run_tick` | one iteration of polling + dispatch (used in tests and as the legacy entry); runs `reconcile_pending_review()` before normal stale-running/candidate polling when dispatch state is present |
| `_dispatch_one` | claim → create worktree → render prompt → dispatch agent → finalize |
| `_select_scheduled_candidate` | pick due `scheduled`-labeled issue; honours C-0012 label-only fallback |
| `_release_scheduled_candidate` | remove `scheduled` label, write audit comment, dispatch through normal flow |
| `_repair_cancelled_schedule` | reconcile stale `scheduled` label after a cancellation event |
| `_detect_agent_schedule` | agent-emitted schedule command detection from output |
| `reconcile_startup` | one-shot per-binding reconcile from durable signals (worktrees, tmux sessions, Plane Running issues) per [ADR-0003](../analyses/adr-0003-worktree-per-run.md) C-0019 |
| `reconcile_pending_review` | retry post-agent review transition after Plane 429; moves still-Running issues with retained worktrees to In Review without rerunning the agent |
| `reconcile_stale_running` | reclaim stale Running issues, and after `INTERRUPTED_RUNNING_REVIEW_GRACE_S` can retain a Running issue with no in-flight local Run but an existing worktree |
| `reconcile_done_landing` | sweep Done issues whose Run branches need landing per Binding's `landing.mode` |
| `_block_issue` | transition issue to Blocked, post sanitised comment, fire Telegram notification |
| `_notify_review` | fire Telegram on IN_REVIEW transition (C-0015) |
| `_claimed_at` | parse claim comment timestamp |
| `_fetch_issue_comments`, `_fetch_issue_comment_bodies` | paginated comment retrieval |

## Errors

| Class | Raised when |
|---|---|
| `SchedulerError` | engine-level dispatch failure |
| `LockHeld` | another tick is already running (legacy single-flock path) |
| `LandingFailed` | landing step (auto-commit, branch reconcile) failed |
| `AutoCommitFailed` | the `_auto_commit` backstop failed (issue blocked, error reported) |

## Notes / known gaps in this page

- The 2633 LOC body of `scheduler.py` is **not** fully transcribed here. Specific behaviours (sanitisation of stderr, secret redaction via `_collect_secrets`, dirty-base approval protocol details, mode-resolution algorithm) should be ingested as separate concept pages when questions arise.
- `_sanitize_report(text, secrets)` uses `_collect_secrets(config)` to redact PLANE_API_KEY, ZAI_API_KEY, Telegram tokens, etc. from any text written to Plane comments. Trust this layer; never pass secrets to scheduler functions outside that flow.
- Session 2026-06-09 proved post-agent Plane 429 can occur after clean agent exit. The durable fix is `pending_review_issue_ids` plus retained-worktree recovery; the operational fix is shared Plane cooldown plus avoiding optional-label discovery scans [source: wiki/raw/sessions/2026-06-09-trading-smoke-rate-limit.md#durable-facts].

## Related

- [ADR-0003 — worktree-per-run](../analyses/adr-0003-worktree-per-run.md) — the concurrency model this implements
- [Agent runner + worktree](agent-runner-and-worktree.md) — adapters dispatched by `_dispatch_one`
- [Prompt renderer](prompt-renderer.md) — invoked before agent dispatch
- [Schedule comment grammar](schedule-comment-grammar.md) — parser used by scheduled-release path
- [Blocked reconciler implementation](blocked-reconciler-implementation.md) — separate sweep, not part of the main tick
