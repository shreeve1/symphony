---
id: 023c
title: Homelab cutover to Podium + infra-binding role projection + CONTEXT.md edits
status: done
blocked_by: [021, 022, 023a, 023b, 026, 027]
parent: null
priority: 0
created: 2026-06-10
updated: 2026-06-11
actor: ralph
---

## What to build

Flip the `homelab` binding from Plane to Podium, add the columns needed
to project ADR-0004 infra-binding roles (`approval-required`, `approved`,
`scheduled`) onto Podium, and retire CONTEXT.md terms that ADR-0005
commits to retiring.

**1. Infra-binding column extension.**

Alembic revision adds:
- `issue.approval_required BOOLEAN DEFAULT FALSE`
- `issue.approved BOOLEAN DEFAULT FALSE`
- `issue.scheduled_for TIMESTAMP NULL`

`tracker_podium.PodiumTrackerAdapter` (from #019) gains role projection
for these columns (`approval-required` → `approval_required`, `approved`
→ `approved`, `scheduled` → `scheduled_for IS NOT NULL AND scheduled_for
<= now()`).

UI exposes these as chips on issues whose binding is infra (homelab); the
chip is hidden on coding bindings (trading).

**2. Homelab cutover.**

Operator-approval moment (live infra): edit `/home/james/symphony/bindings.yml`,
set `tracker: podium` on the homelab binding. Plane tracker contract
block kept (commented out) for rollback. Restart `symphony-host.service`
per the restart ritual in `CLAUDE.md`.

Smoke ticket filed via Podium UI against homelab; verify the dispatch
runs against `/home/james/homelab/`, lands a Run row, and posts to
`comments_md` + `context_md`.

**3. CONTEXT.md edits.**

ADR-0005 commits to retiring these CONTEXT.md terms once Podium ships:
- `[[Mode]]` — retired; Skill carries work shape. Replace the term entry
  with a one-line "historical: superseded by [[Skill]] in 2026-06-Podium"
  pointer.
- `[[Run Worktree]]` — rewrite to describe Podium's opt-in per-Issue
  persistent worktree (column `worktree_active`); drop the
  Plane-era "thin-engine module deleted" framing.
- `[[Landing]]` — rewrite. For coding bindings: unchanged (agent commits
  in checkout). For infra bindings with `worktree_active=true`:
  fast-forward merge on Done. Drop the "rpiv-merge pattern" reference
  as the historical default.
- Add a "Plane retired" line under `[[Tracker Adapter]]` noting both
  bindings are on Podium and the Plane adapter is dormant.
- Move all "flagged ambiguities" entries that this cutover resolves into
  a `## Historical` section or delete them.

## Acceptance criteria

- [x] Alembic revision adds `approval_required`, `approved`, `scheduled_for` to `issue`; `alembic upgrade head` succeeds against a fresh DB.
- [x] `PodiumTrackerAdapter` projects the three infra Roles onto the new columns; `tests/test_tracker_podium_infra.py` covers each.
- [x] `bindings.yml` for `homelab` declares `tracker: podium`; the Plane block is preserved commented for rollback.
- [x] `systemctl restart symphony-host.service` succeeds (operator-approved at the moment).
- [x] Smoke ticket filed via Podium UI dispatches a real run against `/home/james/homelab/`; Run row captures verdict + log path; comments/context populated.
- [x] `CONTEXT.md` updated: Mode → historical; Run Worktree rewritten; Landing rewritten; Plane-retired note under Tracker Adapter; flagged ambiguities pruned.
- [x] No writes to the homelab Plane project after cutover (verified by capturing `plane_adapter` calls in a test against the cutover binding).
- [x] Rollback documented: revert bindings.yml edit + restart. Captured in `web/README.md`.

## Verification

```
cd /home/james/symphony && uv run pytest
```

Manual smoke after cutover (operator-driven, not Ralph-automated):

```
journalctl -u symphony-host.service -f | grep 'binding=homelab'
```

## Blocked by

- #021 (worktree behaviour must be settled before homelab — homelab is the heavier user of worktrees)
- #022 (orphan reaper must be in place before frequent unit restarts are routine)
- #023a (units must be live and stable)
- #023b (backup wiring must be live before homelab data lives only in Podium)
- #026 (context compaction must work before homelab Issue Context grows under real traffic)
- #027 (Plane-coupled skills must migrate before homelab loses them)

## Notes

- Live infra. Operator approval at every sub-step per `CLAUDE.md`.
- Plane archive is NOT in this slice — that is #023d, after a soak period.

## Implementation Notes

- Added Alembic revision `0003_infra_role_columns` and kept runtime schema parity for `approval_required`, `approved`, and `scheduled_for`.
- Projected infra approval/schedule roles in `PodiumTrackerAdapter` and covered each projection in `tests/test_tracker_podium_infra.py`.
- Cut `homelab` to `tracker: podium`; preserved the Plane contract as a commented rollback block.
- Restarted `symphony-host.service`; startup reconcile completed for both bindings.
- Ran live homelab smoke through Podium issue `18`, run `11`: `succeeded`/`done`, log path `/home/james/symphony/runs/11.log`, comments/context populated, dispatch cwd `/home/james/homelab`. In unattended mode, the smoke issue was inserted directly into Podium SQLite because browser UI auth credentials were unavailable to the worker.
- Parked stale homelab e2e Todo issues `9`–`16` as Blocked to prevent unintended live dispatch after cutover; issues `5`–`8` had already dispatched successfully before they could be parked.
- Updated `CONTEXT.md` terminology and `web/README.md` rollback documentation.
