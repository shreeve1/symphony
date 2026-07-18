---
status: accepted
supersedes-part-of: ADR-0038 (spawn terminus + loop terminus landing)
amended-by: 2026-07-18 (worktree-off spawn branch-mismatch guard, Option B extension)
relates-to: ADR-0014 (operator-gated worktree landing), ADR-0020 (verified-close direct-done), ADR-0023 (provenance-gated auto-land), ADR-0038 (spawn/loop modes), ADR-0040 (automation pin fields)
decided-with: James, 2026-07-17 (Podium issue #468 loop-lifecycle grill)
---

# Automation terminal landing: spawn auto-close, loop failure retry

## Context

ADR-0038 shipped spawn and loop automations with a deliberately conservative
terminal contract: every loop terminus (completion marker or cap) parks the
Issue in `in_review` and never lands unattended, and spawn Issues "follow the
normal lifecycle" — which in practice means a passing spawn Issue parks in
`in_review` awaiting a manual operator merge, because spawn Issues are created
with `auto_land=false` (`tracker_podium.py::fire_due_spawn_automations`).

Walking the loop lifecycle end to end (issue #468) surfaced two gaps that the
`in_review`-always contract does not cover:

1. **Loop failure wedges silently.** `reconcile_loop_automations` only advances
   or terminates a loop when its Issue is `in_review`; any other state hits
   `continue` (`tracker_podium.py:789`). A failed/timed-out/blocked iteration
   lands the Issue in `blocked` (`transition_state`, `tracker_podium.py:456`),
   which is not a dispatch candidate (`tracker_podium.py:222`) and is never
   re-examined by the reconciler. The loop dies with no re-dispatch, never
   reaches its cap, and emits no operator signal.

2. **Spawn one-shots don't self-complete.** Spawn Automations are meant to be
   fire-and-forget one-shot prompts. Parking every passing occurrence in
   `in_review` for a manual merge defeats that intent — the operator wanted them
   to land their work and close to `done` unattended.

## Decision

### Spawn Issues land their work and close to `done`

A passing spawn occurrence commits its work and terminates in `done` unattended,
regardless of the automation's `worktree_active` pin. `in_review` is no longer a
normal spawn terminus.

- **Worktree ON** — reuse the ADR-0023 auto-land pipeline: the agent works in the
  per-Issue worktree, the passing verdict runs review, the worktree branch merges
  to base (`_land_review_worktree`), and the Issue closes to `done`.
- **Worktree OFF** — the agent works directly in the shared base checkout and
  commits its own work there; Symphony detects a clean, committed base checkout
  (`web/api/worktree.py::base_repo_dirty`, `worktree.py:99`) and transitions the
  Issue to `done`.
  There is no merge step because the work is already on the base branch. This is
  **Option B** from the #468 grill: the agent commits to base itself.

  If the agent leaves the base checkout dirty (forgot to commit), reuse the
  existing commit-redispatch pattern (`COMMIT_REDISPATCH_REPLY_PREFIX`,
  `MAX_COMMIT_REDISPATCH`, `redispatch_core.py`): re-dispatch to finish the
  commit, then block after the cap so nothing closes with uncommitted work.

  **Branch-mismatch guard (amended 2026-07-18).** The base-checkout land path
  also gates on `HEAD` matching the candidate's `base_branch`. A clean checkout
  on a stale branch (e.g. one left behind by a previous worktree-merge land or
  a manually-checked-out feature branch) is treated as a degenerate state:
  closing the Issue to `done` would record a verdict on work that landed
  elsewhere. The land path detects this via the new public helper
  `web.api.worktree.base_repo_branch` (local) and
  `remote_worktree.base_repo_branch` (remote); on mismatch it re-dispatches
  with a checkout instruction, then blocks after `MAX_COMMIT_REDISPATCH` —
  same fail-closed contract as the dirty-checkout branch. The gate is opt-in
  (empty `base_branch` returns True) so callers without a pinned base do not
  false-block.

**Accepted risk — shared-checkout concurrency.** Worktree-OFF spawns commit to a
single mutable base checkout with no per-Issue isolation. Two spawns (or a spawn
and any other worktree-off run) touching that checkout concurrently can interleave
commits or collide. The operator accepted this (2026-07-17): worktree-off spawns
are expected to be low-frequency and serialized in practice. Operators who need
isolation set the worktree pin, which routes through the merge path instead. This
is why loop mode still *forces* a worktree — a loop's many iterations cannot
tolerate the race.

### Loop failure re-dispatches a bounded number of times, then terminates

When a loop Issue is `blocked` (failed/timed-out/errored iteration), the loop
reconciler re-dispatches it instead of skipping it forever:

- Count consecutive failures from a `### Symphony Loop Retry` marker in Issue
  Comments, following the existing marker-counting pattern
  (`count_loop_iterations`, `count_commit_redispatches`).
- If fewer than **3** consecutive failures, append a retry marker and flip the
  Issue `blocked → todo` to re-dispatch.
- On the **3rd** consecutive failure, append a `### Symphony Loop Blocked`
  terminal block (worktree preserved for operator review, mirroring the
  cap-reached block) and disable the Automation (`enabled=0`).
- Any iteration that reaches `in_review` resets the consecutive-failure count.

The retry bound (3) is **separate** from the iteration cap: the cap counts
productive iterations; the retry bound counts consecutive failures. A terminated
loop remains disabled with no automatic re-arm (unchanged from ADR-0038); the
operator recreates or re-enables.

## Consequences

- **Reverses ADR-0038's terminal contract.** ADR-0038 said "Both termini park the
  Issue in `in_review`... Neither path sets `done` or invokes `auto_land`" and
  spawn "follows the normal lifecycle." Spawn now auto-closes to `done`; that
  clause of ADR-0038 is superseded here. Loop *success/cap* termini are unchanged
  (still `in_review`); only the new *failure* terminus is added.
- **A new non-worktree land path exists.** Before this, the only automation land
  path was worktree merge (`_land_review_worktree`); no code path committed or
  closed work made directly in the base checkout, and the scheduler's base-dirty
  wrapper `_review_base_repo_dirty` (`scheduler/reland.py:118`) was imported but
  never called. Option B introduces the first automation land path that keys off
  base-checkout state via `base_repo_dirty`. Any future change to landing must
  account for both paths.
- **Loops can no longer wedge on a single failure**, but a genuinely broken loop
  still self-limits at 3 consecutive failures rather than burning iterations or
  looping forever.
- Backend-only change (Python scheduler + tracker); requires a `symphony`
  scheduler restart, not a web deploy.
- **Amendment (2026-07-18):** the spawn-worktree-off land path gained a
  branch-mismatch guard (`_review_base_repo_branch`). The same fail-closed
  contract as dirty-checkout applies: re-dispatch under cap, block at cap.
  Two new public helpers (`web.api.worktree.base_repo_branch`,
  `remote_worktree.base_repo_branch`) follow the existing `base_repo_dirty`
  public/private split rather than duplicating it.
