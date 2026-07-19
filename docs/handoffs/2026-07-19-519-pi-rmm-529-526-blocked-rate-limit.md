# Handoff — pi-rmm bridge issues #529 / #526 blocked (pi Token Plan rate limit)

## Purpose of the next session

Two mirrored pi-rmm issues from the ADR-0042 GitHub⇄Podium bridge smoke are
`blocked` after their pi runs stalled. Diagnose why, decide whether it's a
transient quota exhaustion or a standing config problem, unblock them, and let
the dependency chain drain. **This is a dispatch/agent-runtime + quota issue, NOT
a bridge bug** — the bridge did its job correctly (sync, ordering fix, edges,
origin chip all verified in prior session). Do not re-litigate the bridge.

## Live state at handoff (2026-07-19 ~03:40 UTC)

pi-rmm binding, `github:shreeve1/pi-rmm#*` rows (Podium ids):

| Podium | GitHub | state | auto_land | blocked_by | worktree_active |
|---|---|---|---|---|---|
| #525 | #14 agent rotating log | **done** | 1 | [] | 0 (landed) |
| #526 | #13 stalled-run visibility | **blocked** | 1 | [] | 1 |
| #527 | #12 settings + rename | todo | 1 | [#528] | 1 |
| #528 | #11 Display Name in Fleet+search | todo | 1 | [#529] | 1 |
| #529 | #10 endpoint identity foundation | **blocked** | 1 | [] | 1 |

Dependency chain: #529(gh10) ← #528(gh11) ← #527(gh12). Roots: #529, #526, #525.
**#525 already auto-landed + closed its GitHub issue** (bridge close-back works).
#527/#528 are correctly parked `todo` waiting on their (now-blocked) blockers —
so the whole chain is stalled behind #529.

## Root cause (grounded)

The pi provider (`pi-duo`, model `Duo:high`) hit a **Token Plan rate limit**.
From the run logs:

- `runs/2934.log` (issue #529, first run) stderr:
  `429 {"type":"error","error":{"type":"rate_limit_error","message":"Token Plan
  usage limit reached: Upgrade your Token Plan or purchase Credits for more usage.
  (2056)"}}` → `[rate-limit-retry] provider returned error; treating rate limit as
  retryable.`
- `runs/2940.log` (#529 resume attempt): empty stdout, same 429, plus
  `Warning: No project session found with id 'f8a520c5-…'; creating a new session`.

Scheduler retry sequence for **#529** (all `run` rows): stalled→retry (2934),
stalled→retry (2938), `resume_failed: exit code 1; fell_back=true` (2940),
retry (2942), resume_failed (2944), `Combined retry ceiling exhausted after 3
retries` (2946) → `state=blocked` (scheduler log 03:11:39
`reason=combined-ceiling-exhausted`).

**#526** is subtler and worth noting: its FIRST run (2930) actually
**succeeded with verdict=review** — the agent fully implemented story #13
(new `investigation_stalled` route + audit event + UI + poller catch; see the
long summary in run 2930). But then the review/resume runs (2936–2947) all hit
the same 429 rate limit, stalled, and exhausted the ceiling → `blocked`. So #526
likely has real committed work in its worktree that just never got reviewed/landed.

Both worktrees still exist on disk:
`/home/james/pi-rmm/worktrees/pi-rmm/529/` and `…/526/`.

## What to do next session

1. **Confirm the quota state first.** Check whether the pi Token Plan limit has
   reset (it's a rolling/plan quota — likely time-based). Probe with a cheap pi
   call or check the provider dashboard. Until quota is back, re-dispatching will
   just re-stall. Grounding: `runs/2934.log`, `runs/2940.log`, `models.yml`
   (`Duo:high` / `pi-duo` provider), C-0311/C-0315 (catalog/provider gotchas).

2. **Inspect #526's worktree before unblocking** — it may already contain a
   complete, committed implementation of story #13. Check
   `git -C /home/james/pi-rmm/worktrees/pi-rmm/526 log --oneline main..HEAD` and
   `git status`. If the work is committed and clean, #526 may just need a review
   re-dispatch (not a fresh implement). If dirty/uncommitted, the C-0324/dirty-
   worktree path applies.

3. **Unblock via operator reply / re-dispatch** once quota is restored. An
   `in_review→todo` or `blocked→todo` reply re-dispatches (C-0118). For a blocked
   issue, the reply endpoint flips it to `todo`; the next scheduler tick re-runs.
   Do #529 first (it gates #528→#527). When #529 reaches done, #528 unblocks
   automatically (`_dependencies_satisfied`, tracker_podium.py:350), then #527.

4. **Watch the auto-land + close-back** as each drains: on `done`, the scheduler
   (`symphony-host.service`, already running the bridge code) fires
   `gh issue close <n> --comment "Landed in <sha>."` for each `github:`-prefixed
   row. Verify GitHub #10–#13 close in dependency order; parent #9 stays open
   for `finish-spec`.

## Known-good context (do not re-verify — settled prior session)

- Bridge acceptance walk complete: #513–517 all verified in merged code; full
  suite 1678 pass. See `wiki/analyses/adr-0042-github-podium-dispatch-bridge.md`,
  claims C-0384..C-0388.
- `sync_from_github` ordering fix landed (commit `430e468`): children sort
  ascending by number so blocked_by resolves in one pass (C-0386).
- Synced issues carry `origin="automation"` for a card chip (commit `973ee1d`);
  dedicated `github` origin deferred (needs migration 0025 to widen origin CHECK).
- **Deploy gotcha (C-0388):** both `podium-api` and `podium-web` pin code at
  process start — restart the owning unit after any land touching their code.
  `symphony-host` (scheduler / close-back) is already on current bridge code.
- The dropped-blocked_by edges from the first (stale-code) sync were backfilled
  by hand: #528→[#529], #527→[#528]. These are correct now.

## Guardrails

- **Not a bridge bug.** The failure is provider quota (429) + the normal
  stall/retry/ceiling machinery doing its job (blocking after exhaustion). Don't
  patch the bridge for this.
- Don't force-land #526's worktree without reviewing it — it has real
  auto_land=true work; it must pass the review verification backstop
  (`scheduler/__init__.py` review-terminal path) before it merges to pi-rmm main.
- pi-rmm is a real project repo; auto_land=true means a clean review FF-merges to
  its `main`. Treat merges as real.
