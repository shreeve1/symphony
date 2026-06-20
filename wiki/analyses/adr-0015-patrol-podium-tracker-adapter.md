---
title: ADR-0015 — Route Temporal patrols to Podium via a tracker-agnostic ticket-writer seam
type: analysis
status: promoted
created: 2026-06-20
updated: 2026-06-20
sources:
  - docs/adr/0015-patrol-podium-tracker-adapter.md
  - /home/james/homelab/plans/59.md
  - blocked_reconciler.py
  - web/api/main.py
  - tracker_podium.py
  - wiki/raw/sessions/2026-06-20-patrol-podium-adapter-grill.md
confidence: high
tags: [adr, patrol, podium, plane, tracker-adapter, ticket-writer, external-id, blocked-reconciler, temporal, homelab, cross-repo, proposed]
---

# ADR-0015 — Route Temporal patrols to Podium via a tracker-agnostic ticket-writer seam

`proposed` 2026-06-20. Outcome of a `/grill-me` design pass over homelab
`plans/59.md`. **No patrol→Podium code exists yet** — decision + plan only.
Spans two repos: homelab (`automation/homelab-stack`, patrol worker) and
symphony (Podium API + reconciler).

## Problem

Homelab Temporal patrol workers write findings to **Plane**
(`homelab-stack/src/homelab_worker/worker.py` → `PlaneAdapter`), but Symphony
already moved to **Podium** (ADR-0005). Patrols must post to the Podium board
behind a clean adapter seam, with Plane preserved as a slot-in backend
[source: docs/adr/0015-patrol-podium-tracker-adapter.md].

Podium can't satisfy the patrol lifecycle as-is: the create endpoint is a plain
INSERT with no `external_id`/dedup/labels (`web/api/main.py:807`); comments fold
into one `comments_md` blob surfaced as a single one-timestamp synthetic comment
(`tracker_podium.py:245`); and the reconciler's patrol rule counts discrete pass
comments (`blocked_reconciler.py`, `min_pass_comments_since_fail=2`), impossible
on the single-blob model — so patrol issues would never auto-cure on Podium.

## Decision

A tracker-agnostic `TicketWriter` seam in homelab with a **separate
`PodiumAdapter`** peer to `PlaneAdapter`; hard-cut behind
`PATROL_TRACKER=podium|plane` (default `podium`); **full lifecycle parity**
(create / dedup / reopen / update **and** auto-cure), not just posting.

Six parts:

1. **Neutralize the seam (homelab).** `ticket_writer.py` exists but its Protocol
   uses Plane types (`PlaneState`/`PlaneLabel`/`IssuePayload`); swap to neutral
   `TicketState`/`TicketDomain`/`TicketSeverity` + `TicketWrite`. `patrol_plane.py`
   depends only on neutral types; activity names (`record_patrol_*`) unchanged,
   so no Temporal workflow signature change. `PlaneAdapter` gains neutral shims.
2. **Separate `PodiumAdapter` + `podium_http.py` (homelab).** Implements
   `TicketWriter` over HTTP to `podium-api.service`. Neither adapter imports the
   other. severity→priority `{CRITICAL:urgent, HIGH:high, MEDIUM:med, LOW:low}`
   (note `med`, not `medium`); state `{TODO:todo, DONE:done, BLOCKED:blocked}`.
   Domain/severity stay in the `<!-- patrol-status: ... -->` marker — no columns.
3. **`external_id` dedup (Symphony — excluded service).** Migration adds
   `external_id TEXT` + a **global-unique nullable** index; `IssueCreate`/
   `IssuePatch` accept + persist it; `GET /api/bindings/{name}/issues?external_id=`
   filter mirrors Plane. Global (not composite with `binding_name`) because the
   sha-hash ids are already globally unique and both the adapter and reconciler
   treat `external_id` as a global key. The column does **double duty**: adapter
   dedup AND reconciler rule selection (`external_id_prefix="homelab-patrol-"`).
4. **Cure parity (Symphony — excluded service).** New Podium-only
   `patrol-passes-marker` reconciler rule reads the marker from
   `issue["description"]` (already `SELECT *`-ed) and fires on
   `consecutive_passes >= 2 AND last_pass_at > last_fail_at`. The patrol marker
   gains `last_pass_at`/`last_fail_at` (homelab). The Plane comment-counting rule
   is retained for Plane.
5. **`homelab-patrol` binding** in `bindings.yml`; **auto-dispatch all** findings.
6. **Per-state adapter contract:** `done`→reopen to `todo`; `blocked`→
   evidence-only (reconciler cures); `running`/`in_review`→never touch state;
   none→create.

## The marker-trust reversal (why it's safe on Podium)

C-0014 / C-0035 say the reconciler ignores `consecutive_passes` because Plane
resets it to 1 each cycle. The root cause is an **editor bug**: Plane's
rich-text editor strips HTML comments from `description_html` on round-trip
(`patrol_plane.py:65-71,256-261`; observed live 2026-05-18), not patrol logic.
Podium stores `description` as plain markdown — no editor round-trip — so the
marker survives and the counter increments. The marker rule is therefore
**additive and Podium-scoped**; the Plane stance stays correct for Plane. This
is the one genuinely surprising, hard-to-reverse decision in the ADR.

## Build sequencing (A→B→C)

Re-sequenced from plan 59's literal 1→4 to pay the excluded-service restart once
and de-risk the migration:

- **Wave A (homelab, no service impact):** neutralize seam; add marker
  timestamps; build `PodiumAdapter` + transport; unit-test against in-memory
  Podium transport.
- **Wave B (Symphony, ONE gated `podium-api` window):** `external_id` migration
  + endpoint + filter, `patrol-passes-marker` rule, `homelab-patrol` binding —
  batched, adapter contract already mock-proven.
- **Wave C (cutover + verify):** wire `worker.py` + toggle; dry-run create /
  reopen / update / cure on Podium; restart the patrol worker.

## Rejected alternatives

Composite `UNIQUE(binding_name, external_id)` (redundant under sha-hash global
ids); `domain`/`severity` columns (marker already round-trips on Podium); Tier 1
only / defer cure (reproduces the Blocked pile-up the reconciler exists to
prevent); patrol worker self-closes (duplicates cure logic outside the seam);
schema-before-adapter per plan 59's literal order (risks a second gated restart).

## Consequences / status

- Plane stays a working slot-in backend (`PATROL_TRACKER=plane`).
- Cross-repo: homelab and symphony commit independently to their own `main`.

**Build status (2026-06-20, via `/dev-build`):** Waves A + B built, tested,
committed, **inert** (nothing applied/restarted).
- Wave A — homelab `e86d69d`: neutral `ticket_types.py` seam + `PodiumAdapter`/
  `podium_http.py` (imports only `ticket_types`, verified) + marker
  `last_pass_at`/`last_fail_at`. pi audit clean; 172 targeted pass.
- Wave B — symphony `44d6b5f`: migration `0009` (`external_id` + global-unique
  nullable index, idempotent), schema parity, `external_id` on create/PATCH +
  UNIQUE→409, `?external_id=` filter, marker-first reconciler cure. pi audit 0
  critical / 2 warnings (auto-fixed); full suite 966 passed.
- **§4 revised during build:** cure shipped as a *unified marker-first-with-
  comment-fallback inside the existing patrol rule* (not a separate
  `patrol-passes-marker` `DEFAULT_RULES` entry) — the reconcile call site passes
  no per-tracker rules, so consolidation avoids plumbing tracker-kind; the Plane
  comment path is byte-for-byte preserved (marker only survives on Podium).
- **Binding routing revised 2026-06-20 (C-0267):** patrols post to the
  **existing `homelab` binding**, not a new `homelab-patrol` binding (mirrors the
  Plane setup; drops the scaffold + new WORKFLOW.md prereqs). No Wave A/B code
  change — `PodiumAdapter(binding="homelab")` is Wave C wiring; dedup
  (`?external_id=` AND `binding_name=homelab`) and the reconciler rule (keyed on
  the `homelab-patrol-` external_id prefix) stay correctly scoped.
- **Gated `podium-api` window APPLIED LIVE 2026-06-20 at full parity (C-0268).**
  Migration 0009 applied to live `podium.db` (0008→`0009 (head)`; `external_id`
  column + `ix_issue_external_id` index present); `podium-api` restarted (Wave B
  endpoint live — `?external_id=zzz`→200 `[]`); `symphony-host` restarted
  (`symphony_started`/`reconcile_startup_completed`×5/`dispatch_completed`; cure
  live — `blocked_reconcile_skipped issue_id=61 external_id=`). `homelab` binding
  unchanged. Backup `/backup/podium-2026-06-20.db`. **No new binding/WORKFLOW.md**
  (C-0267). Two ops facts: alembic config is at repo ROOT (`-c alembic.ini`, not
  `web/api/alembic.ini`); migration MUST precede the podium-api restart or Wave B
  startup crashes on `_schema_drift` missing-column. Benign nit: `INITIAL_REVISION`
  left at 0008 → per-startup `podium_schema_revision_mismatch` warning (non-fatal).
- **Auth gap found + closed during Wave C (C-0269, symphony `69bf3f3`, 2nd gated
  window).** podium-api was cookie-only; Wave A's Podium transport speaks Bearer.
  Added an optional `PODIUM_API_TOKEN` Bearer path to the `require_auth`
  middleware (constant-time, cookie-fallback, unset→cookie-only). Token set in
  `symphony-host.env` + podium-api restarted; verified bearer→200 / bad→401 /
  cookie→200.
- **Wave C built + dry-run-verified, worker cutover DEFERRED (C-0270, homelab
  `d160955`/`2e4fad6`).** `worker.py` selects `PodiumAdapter(binding=homelab)` vs
  `PlaneAdapter` via `WorkerConfig.patrol_tracker` (default `podium`); new podium
  config fields; `PODIUM_API_TOKEN` required when tracker=podium. Live dry-run
  (10/10) caught + fixed a real bug — `find_by_external_id` didn't parse the live
  API's bare-list response (mock returned `{"results":[...]}`). Marker round-trip
  confirmed live (C-0265). **Remaining:** worker env (`PODIUM_API_TOKEN` +
  `PATROL_TRACKER=podium`) + restart `homelab-temporal-patrol-worker.service` —
  operator paused after the dry-run; patrols still on Plane until then.
- See C-0266 / C-0267 / C-0268 / C-0269 / C-0270.

## Related

- [ADR-0002 — generalize Symphony behind adapter seams](adr-0002-generalize-symphony.md)
- [ADR-0005 — replace Plane with Podium](adr-0005-replace-plane-with-podium.md)
- [Blocked reconciler implementation](../concepts/blocked-reconciler-implementation.md)
- [Podium tracker](../concepts/podium-tracker.md)
- Claims C-0263 / C-0264 / C-0265; notes on C-0014 / C-0035.
