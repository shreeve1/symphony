# Session — grill-me: wire Temporal patrols to Podium (2026-06-20)

Curated capture of a `/grill-me` design pass over `/home/james/homelab/plans/59.md`
("Route Temporal patrols to Podium via a tracker-agnostic adapter"). No
patrol→Podium code exists yet; this is plan + decisions. Produced ADR-0015.

## Grounding (verified this session)

- Patrol worker still writes Plane: `homelab-stack/src/homelab_worker/worker.py`
  → `PlaneAdapter(transport=...)`.
- A seam already exists but is Plane-typed: `homelab-stack/src/homelab_router/
  ticket_writer.py` defines a `TicketWriter` Protocol whose methods use
  `PlaneState`/`PlaneLabel`/`IssuePayload`/`CommentPayload`. Wave A must
  neutralize these.
- Patrol marker (`patrol_plane.py:104-168`, `base_metadata`) is JSON,
  last-marker-wins, carries `external_id, domain, severity, latest_status,
  consecutive_passes` — **no timestamps**.
- `stable_external_id` = `homelab-{runbook}-{sha256[:8]}` (`plane_adapter.py:21`).
  `PlaneAdapter.find_by_external_id` queries `?external_id=` globally.
- Podium create endpoint (`web/api/main.py:807`): plain INSERT forced
  `state='todo'`, extra fields → 400, no `external_id`/labels.
- `PodiumTrackerAdapter.list_comments` (`tracker_podium.py:245`) returns the
  whole `comments_md` blob as ONE synthetic comment with ONE timestamp.
- Reconciler patrol rule (`blocked_reconciler.py:123-131`, `_evaluate_rule`)
  counts DISTINCT pass comments since the latest fail
  (`min_pass_comments_since_fail=2`); deliberately ignores `consecutive_passes`
  because Plane resets it to 1 each cycle (C-0014/C-0035).

## Linchpin established

The Plane "`consecutive_passes` always = 1" bug is an **editor-strip bug**, not
patrol logic: Plane's rich-text editor strips `<!-- patrol-status -->` HTML
comments from `description_html` on round-trip (`patrol_plane.py:65-71,256-261`;
live 2026-05-18). Podium stores `description` as plain markdown → marker survives
→ `consecutive_passes` increments. So trusting the marker on Podium is sound
even though it is unreliable on Plane.

## Decisions (settled with James)

1. Full lifecycle parity (incl. auto-cure), not just posting. James: "agreed".
2. `external_id` global-unique nullable index (not composite). James: "agree".
3. Sequencing A→B→C, both excluded-service changes batched into one gated
   `podium-api` window. James: "accepted".
4. Architecture clarified by James: clean Plane/Podium adapter separation behind
   one neutral seam, both deployable, multi-platform; success = patrols post to
   the Podium board.

Carried forward from the prior grill (not re-litigated): auto-dispatch all;
per-state adapter contract (`done`→reopen, `blocked`→evidence-only,
`running`/`in_review`→never touch, none→create); cure trusts marker +
timestamp guard.

## Gap surfaced

Plan 59's original Wave 2 listed only migration + endpoint + external_id filter +
binding — it **omitted the reconciler change**. Fork 3 (marker-trusting cure)
requires a NEW `patrol-passes-marker` rule inside `blocked_reconciler.py` (an
excluded-service touch) AND the patrol marker to gain `last_pass_at`/
`last_fail_at`. Now folded into Wave B + Wave A.2.

## Artifacts produced

- `docs/adr/0015-patrol-podium-tracker-adapter.md` (status `proposed`).
- `plans/59.md` updated: settled-decisions block, Waves re-sequenced A→B→C,
  approval checklist resolved (homelab repo, commit pending).
- Next: `/dev-build` Wave A (homelab, no service impact).
