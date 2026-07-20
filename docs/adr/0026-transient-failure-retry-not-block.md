---
status: proposed
relates-to: ADR-0024 (review-mode gate + dirty commit-redispatch — supplies the reland/marker machinery the review-retry path reuses), ADR-0023 (native per-issue review phase), ADR-0014 (worktree commit-redispatch — the comments_md marker-counting precedent), ADR-0006 (engine state surfaced by polling), ADR-0021 (parallel Podium issue landing / dependency + lock gates)
decided-with: James, 2026-06-25 (grill-me after Codex `server_is_overloaded` 503s permanently blocked Podium issues #128/#129/#131, plus auto-land/rebase/claim-ID roadblocks on #130/#131)
---

# Transient terminal failures retry / re-drive instead of blocking

## Context

`_classify_terminal` (`scheduler/__init__.py`) maps **every** nonzero agent exit
and every timeout to a permanent `blocked` state with `verdict=blocked`. There is
no distinction between a real code defect and a transient infrastructure failure
(provider overload, rate limit, 5xx, connection reset, a hung run that timed out).

This surfaced live: a Codex `server_is_overloaded` 503 exited the agent with code
1 on issues #128 and #129. Both blocked permanently and had to be manually
recovered — #128 requeued to `todo` (its implement work was uncommitted WIP), and
#129 (whose implement run had already committed and passed tests) needed its
`### Symphony Review` marker stripped and a flip back to `in_review` so the review
run would re-dispatch. The only existing auto-recovery, the `blocked_reconciler`,
is patrol-specific (it cures `homelab-patrol-*` external_ids by counting pass
markers) and never touches an agent-failed coding issue.

The whole point of the dispatch loop is unattended operation. A transient provider
hiccup forcing manual board-shuffling defeats that.

## Decision

Catch transient failures **at the terminal classifier** (agent exit/timeout) and at the **auto-land terminal** (rebase fixed / claim-renumbered branch now landable), and at **startup probe** (transient pi probe timeout) and retry/re-drive instead of blocking/crash-looping. The richest signal — the failed process's own stderr — is available
exactly there, and retrying at the terminal means the issue never visibly hits
`blocked`, so there is no board churn to babysit.

1. **Terminal-classifier retry, not a reconciler sweep.** The retry lives inside
   `_classify_terminal`'s `timed_out` and `exit_code != 0` branches. A
   blocked-column reconciler rule (re-deriving intent from comment text after the
   fact) was rejected — it overlaps the patrol-only reconciler and acts only after
   the issue already churned to `blocked`.

2. **Allowlist of transient signatures, not a denylist.** Retry only when the
   failure matches a known-transient signature; everything else blocks exactly as
   today. The set (matched against captured stderr / the error payload):
   `server_is_overloaded`, `service_unavailable`, `overloaded`, startup probe timeout, rate-limit / `429`,
   `502` / `503` / `504`, connection reset / connection error, and
   `result.timed_out`. A real code defect is the common case for a nonzero exit, so
   the allowlist errs toward blocking: a *new*, unlisted transient string blocks
   once (operator recovers, we add the pattern) rather than retrying genuine
   defects N times and burning ~2 agent runs each only to block anyway. The
   allowlist stays auditable — what triggers a retry is readable in one place.

3. **Timeout is retryable but capped lower.** `result.timed_out` is ambiguous —
   a transient hang (retry-worthy) vs. a stuck loop / oversized task (retrying
   wastes a full run-timeout window). Timeouts retry with a **lower cap (1)** than
   overload/rate-limit/5xx (**2**), since a re-timeout is expensive and more likely
   to indicate a real problem.

4. **Requeue target depends on which run failed (the #129 lesson).**
   - A failed **implement** run → requeue to `todo`. The resume machinery
     reattaches any committed work; uncommitted WIP survives in the worktree.
   - A failed **review** run → must re-enter as a *review*, not an implement.
     Because the `### Symphony Review` marker is already written, flipping to
     `in_review` alone does not re-dispatch (the `tracker_podium.list_candidates`
     `review_dispatch` predicate requires the marker absent or an unconsumed
     reland-pending). The review-retry therefore **reuses ADR-0024's reland/marker
     accounting** rather than inventing a parallel marker-strip — it leaves the
     issue `in_review` and writes the same reland-pending signal that re-enables a
     review dispatch. This couples the review-retry path to ADR-0024 slice #132.

5. **Attempt counter via a `comments_md` marker, not a schema column.** A distinct
   `### Symphony Retry (transient · N)` marker is appended on each retry and counted
   the same way `_count_commit_redispatches` counts auto-commit markers (ADR-0014
   precedent). No Alembic migration; survives restarts; visible in issue history.
   Over the per-class cap → block as today, with the worktree intact and the final
   block comment naming the exhausted retry count.

6. **Modest fixed cooldown, not exponential backoff.** The scheduler is
   poll-driven (ADR-0006). The retry marker is written and the issue requeued
   immediately, but re-selection is suppressed until a fixed cooldown (≈60s) after
   the retry marker's timestamp, so a same-tick re-selection does not just re-hit
   the still-overloaded provider. Overloads clear fast and the poll cadence already
   spaces work out, so exponential backoff is unwarranted.

7. **Silent on retry; notify only on final block.** A mid-retry Telegram ping is
   exactly the babysitting noise this removes. Notification fires only when the cap
   is exhausted and the issue actually blocks.

8. **Scope: all binding types.** 503s hit coding and infra bindings alike; the
   retry applies to both. The real-defect path (non-transient nonzero exit, or
   post-cap exhaustion) is unchanged.

9. **Auto-land can re-drive when the branch becomes landable.** Issues #130 and
   #131 showed a second terminal class: review passed, but auto-land blocked on an
   advanced base / wiki conflict. ADR-0014/ADR-0021's rebase retry can make the
   branch FF-able, but the issue can remain `blocked` because nothing re-drives
   `land_worktree`. When merge/rebase conflict resolution yields a clean,
   FF-able branch, the scheduler should retry/re-drive the land once instead of
   requiring a human to call `land_worktree` and flip the DB. Genuine conflicts
   still block.

10. **Concurrent wiki claim IDs are not concurrency-safe.** #131 collided with an
    unrelated live C-0327 claim. Recovery required renumbering the issue's claim
    to C-0328 during rebase, then #132 added C-0329/C-0330. Future unattended
    wiki updates need either deterministic collision handling during rebase or a
    claim allocator that does not rely on each branch picking "next free integer"
    independently. Until then, claim-ID collision is treated as an auto-land
    re-drive/renumber case, not a code defect.

11. **Startup probe transient failures should not crash-loop the host.** After
    deploying ADR-0024 (`0ca14fe`), `verify_pi_support` timed out twice on
    `pi --print ... ping`; systemd restarted the service until a later probe
    passed. The process eventually became healthy, proving the failure was
    transient, but a transient probe timeout still crashed the dispatcher. ADR-0026
    should treat startup probe timeouts like terminal transients: bounded retry /
    fail-soft per binding, not immediate process death.

    **Amendment (2026-07-20, C-0395):** for Podium bindings, even fail-soft
    per-binding probing has the wrong blast radius: a quota cooldown on the
    catalog default skipped the whole binding while queued Issues selected a
    different healthy model. Podium therefore does not run a provider/model
    print probe at startup. The global Pi RPC capability probe remains, and the
    dispatch gate resolves and validates the model selected by each Issue. The
    bounded startup provider/model probe remains only for local non-Podium Pi
    bindings.

## Shippable in two independent pieces

- **Implement-run retry** (the #128 case, and the common one) is fully independent
  — requeue to `todo` + count the marker — and lands **now**, ahead of the
  ADR-0024 batch, to stop most of the babysitting immediately.
- **Review-run retry** (the #129/#131 case) reuses ADR-0024 slice #132's reland-marker
  accounting and lands **with or after** #132.
- **Startup-probe retry/fail-soft** handles transient `verify_pi_support` timeouts before the scheduler crash-loops.
- **Auto-land re-drive** (the #130/#131 land-block case) lands after the branch is
  cleanly rebased/renumbered and FF-able; if there is a genuine conflict, it stays
  blocked for human resolution.

## Consequences

- An issue hit by a provider hiccup self-heals instead of stranding in `blocked`.
- ~Nx agent spend on a genuinely transient failure before it eventually blocks (N
  bounded by the per-class cap). Acceptable: the alternative is manual recovery.
- A misclassified-transient failure that is actually a defect retries N times and
  still blocks — bounded by the cap, surfaced in the final block comment.
- Review-retry is **coupled to ADR-0024 #132**; it cannot land before the
  reland-marker machinery exists. Implement-retry has no such coupling.
- The retry marker adds run history to `comments_md`; the run-record trail shows N
  failed runs before success/block (downstream `latest_verdict` consumers already
  tolerate multiple runs per issue, ADR-0023).
- **Not retroactive.** Issues already blocked before this lands (e.g. #128/#129/
  #123 at decision time) are not auto-swept — terminal-retry only catches failures
  after it ships. A one-shot backfill sweep is deferred unless a stale-transient-
  block backlog appears.
- Claim-ID collision handling becomes part of the unattended landing story; a
  branch-local `next free C-ID` is not safe under parallel agents.
- Podium startup is independent of default-provider availability; a provider failure is scoped to Issues selecting that provider. Local non-Podium bindings retain bounded probe retry/fail-soft behavior.

## Considered options

- **Blocked-reconciler rule that requeues transient-blocked issues** — rejected:
  acts only after the issue churns to `blocked`, must re-derive intent from comment
  text, and overlaps the patrol-only reconciler.
- **Denylist (retry everything except known defects)** — rejected: retries genuine
  defects, burning agent runs and muddying history; failure mode is churn, not the
  allowlist's self-correcting one-time block.
- **Treat timeout as non-retryable (block as today)** — rejected: many timeouts are
  transient hangs; the lower cap (1) bounds the expensive re-timeout case.
- **Exponential backoff / a durable retry-schedule table** — rejected as
  over-engineered for fast-clearing overloads against a poll loop; a fixed cooldown
  off the marker timestamp suffices.
- **One unified marker shared with the redispatch/reland counters** — rejected: the
  retry count must be distinguishable from commit-redispatch and reland counts (they
  have different caps and meanings), so it gets its own marker.
