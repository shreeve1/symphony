---
id: 98
title: MANUAL — homelab block→schedule policy + dedup-don't-clobber (cross-repo)
status: pending
blocked_by: [94, 95]
parent: null
priority: 0
created: 2026-06-21
---

## What to build

**MANUAL / cross-repo** — this work lives in the homelab repo
(`/home/james/homelab`, separate `main`), which Ralph cannot build from the
symphony worktree. Execute by hand once the symphony marker (#94) + handler (#95)
are live. This is the policy half of ADR-0018 (mechanism = symphony; host policy =
host CLAUDE.md, per ADR-0016).

1. **Block→schedule policy** (`/home/james/homelab/CLAUDE.md`): for medium-risk
   scheduled updates (package/image updates, window-scheduled reboots, prunes — per
   the runbook risk classification) the patrol agent emits `SYMPHONY_SCHEDULE:
   not_before=next_window reason="..."` (the symbolic value — the agent must NOT
   compute or emit a natural-language timestamp; the scheduler resolves the window)
   instead of `SYMPHONY_RESULT: blocked`. High-risk findings still block. A rendered
   "Schedule Context" in the prompt means the agent is in the approved window —
   apply the update.
2. **Dedup-don't-clobber** (`automation/homelab-stack/src/homelab_worker/patrol_plane.py`,
   `record_failure` `:306`): if the matched Podium issue is already scheduled, post
   evidence only — do not reopen, reschedule, or reset the schedule. Detect via
   **Podium fields, not labels** (the homelab `PodiumAdapter` ignores Podium
   labels): the issue row exposes `scheduled_for` (non-null/due) with
   `state == "todo"`, or a parsed `Symphony-Schedule:` control line in
   `comments_md`. Extends the ADR-0015 per-state contract (scheduled-pending ≈
   in-flight).
3. **`record_pass` on a scheduled issue (gap fix):** a held-scheduled issue is
   `todo`, so it is neither done nor blocked and `record_pass` (`:394`) falls
   through the normal open path — below threshold it posts a pass comment (fine), at
   threshold it closes to Done. Make the close **clear the schedule**
   (`scheduled_for`/cancel) so a closed-then-reopened issue carries no stale
   schedule; below-threshold passes stay evidence-only and leave the schedule
   intact. Detect scheduled state via `scheduled_for` on the row.
4. Add homelab-stack regression tests for items 1–3, and update the
   `InMemoryPodiumTransport` mock to enforce the schedule/hold semantics (mirrors
   the C-0270/C-0279 mock-divergence lessons).

**Rollout (operator, per ADR-0018):** ship + verify the symphony marker/apply path
on one real finding BEFORE flipping the homelab CLAUDE.md to hands-off, to bound the
unattended live-infra blast radius. **Then re-open the existing medium-risk blocked
backlog** (issues 63/66/71/74/75/76 et al.) to `todo` — blocked tickets are
operator-owned and never re-dispatch, so without a one-time re-open they stay blocked
forever and never get a chance to emit `SYMPHONY_SCHEDULE`. Do this AFTER the
block→schedule policy (item 1) is live, or they immediately re-block.

## Acceptance criteria

- [ ] `/home/james/homelab/CLAUDE.md` documents the medium-risk block→schedule policy with the symbolic `next_window` value and the "schedule context = authorized to apply" rule; high-risk still blocks.
- [ ] `record_failure` on an already-scheduled Podium issue posts evidence only (no reopen/reschedule/reset), detected via `scheduled_for`+`state=todo` (not labels).
- [ ] `record_pass` close on a scheduled issue clears the schedule; a below-threshold pass leaves it intact.
- [ ] Homelab-stack regression tests cover the schedule emission, dedup-don't-clobber, and record_pass-clears-schedule paths; the `InMemoryPodiumTransport` mock enforces the hold semantics.
- [ ] Verified after #94/#95 are deployed: one real medium-risk finding schedules into the window and applies in-window (operator-observed before broad rollout).
- [ ] The existing medium-risk blocked backlog is re-opened to `todo` (after item 1 is live) and converts to scheduled on the next patrol cycle rather than staying blocked.

## Verification

MANUAL (cross-repo): in `/home/james/homelab/automation/homelab-stack`, run
`uv run pytest` for the homelab-stack suite. Symphony's Ralph loop does not build
this issue — mark done by hand after the homelab commit + verification.

## Blocked by

- Blocked by #94 (the `SYMPHONY_SCHEDULE` marker must exist) and #95 (the scheduler handler must process it).
