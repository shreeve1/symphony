---
title: ADR-0015 — Route Temporal patrols to Podium via a tracker-agnostic ticket-writer seam
type: analysis
status: promoted
created: 2026-06-20
updated: 2026-06-20
last_event: 2026-06-20 reply-409 self-heal regression + close stickiness (C-0279–C-0281)
sources:
  - docs/adr/0015-patrol-podium-tracker-adapter.md
  - /home/james/homelab/plans/59.md
  - blocked_reconciler.py
  - web/api/main.py
  - tracker_podium.py
  - automation/homelab-stack/src/homelab_router/podium_adapter.py
  - automation/homelab-stack/src/homelab_worker/schedule_patrols.py
  - /home/james/homelab/WORKFLOW.md
  - wiki/raw/sessions/2026-06-20-patrol-podium-adapter-grill.md
  - wiki/raw/sessions/2026-06-20-patrol-podium-cutover-verify-and-fixes.md
  - wiki/raw/sessions/2026-06-20-patrol-podium-reply-409-and-close-stickiness.md
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
  confirmed live (C-0265).
- **CUTOVER COMPLETE (2026-06-20, C-0270).** Worker env got
  `PODIUM_API_TOKEN`+`PATROL_TRACKER=podium`; `homelab-temporal-patrol-worker.service`
  restarted clean (`patrol_tracker=podium binding=homelab`, no 401). **ADR-0015
  fully landed** — patrols now write to the `homelab` Podium binding; first live
  write on the next Temporal-scheduled cycle. Plane retained as a slot-in backend
  (`PATROL_TRACKER=plane`).
- See C-0266 / C-0267 / C-0268 / C-0269 / C-0270.

**First-live-cycle verification + post-cutover fixes (2026-06-20, C-0271–C-0275).**
The scheduled cutover criterion ("first write on the next Temporal cycle") was
unreachable because **all six patrol schedules are created paused by design**
(`schedule_patrols.py:111`; explicit unpause is a separate step Wave C skipped) —
C-0274. An operator-approved manual `infra` patrol then exposed the real gap:

- **Int-id wedge (C-0271).** Live podium-api returns INTEGER issue ids, but
  `TicketActivityOutcome.issue_id` is typed `str | None`, so Temporal failed to
  decode the activity result (`Failed converting to str | None from 62`) and
  retried the workflow task forever. The Podium write itself succeeded (issue 62
  created, dedup-clean, marker + `med` priority correct) — only the workflow
  wedged. Mock/real divergence (the in-memory transport stringifies ids; the
  dry-run had no real id) masked it, exactly like the C-0270 bare-list bug. Fixed
  by `PodiumAdapter._coerce_row_id` (homelab `a716349`) + 2 regression tests;
  re-verified live: workflow `COMPLETED`, ids round-trip as strings.
- **Auto-remediation confirmed + accepted (C-0272).** Each finding auto-dispatches
  a pi agent (`gpt-5.5:high`, `cwd=/home/james/homelab`) that remediates the live
  host (issue 62: journal vacuum, syslog truncation, docker/cache prune, `/`
  86%→79%). One `infra` patrol = 10 findings → 10 dispatches. Operator accepts.
- **Plane-CLI residue retired (C-0273).** homelab `WORKFLOW.md` still told the
  agent to call `plane done|review|blocked`; now routes completion solely through
  the `SYMPHONY_RESULT` verdict (rule 21). homelab `a716349`.
- **All 6 schedules unpaused (C-0274)** via `schedule_patrols unpause --live
  --worker-deployed`; infra next fires 15:00 UTC.
- **Host-global pi break (C-0275).** A broken `ponytail` pi extension (CJS
  `require` in a `type: module` package) aborted every pi dispatch host-wide until
  the operator added a `createRequire` shim. Tangential to the cutover.

## First scheduled-cycle soak — reply-409 self-heal regression + close stickiness (2026-06-20, C-0279–C-0281)

The first **scheduled** infra cycle (15:00 UTC, `patrol-infra-scheduled`) exposed
a regression the manual create-only verification (C-0271) could not reach,
because it only fires on the *second* failure of an existing issue (the reopen
path):

- **Self-heal 409 (C-0279).** `record_failure`'s reopen path flipped the issue to
  `todo` (`update_issue`) and *then* posted the failure comment via `/reply`.
  But `/reply` (`web/api/main.py:1135-1158`) is the operator-reopen endpoint: it
  appends the comment AND flips `state='todo'`, gated to
  `state IN ('in_review','blocked','done')` with no active run. The prior TODO
  flip made the issue non-repliable → deterministic 409 → unhandled
  `raise_for_status` → `record_patrol_check_result` fails → **workflow FAILED**,
  starving every check after the first reopened issue. Dedup held (no dups).
- **Close never stuck (C-0280).** Sibling bug: `record_pass`'s close path set
  `state=DONE` then posted the close comment via `/reply`, which reopened the
  closed issue to `todo`. Auto-cure-to-done bounced straight back out (issue 62
  `closed`→`done`→`todo`→`in_review`), re-dispatching pi each cycle.
- **Both masked by the same mock/real divergence class as C-0270/C-0271:**
  `InMemoryPodiumTransport`'s `/reply` fake appended unconditionally and never
  409'd, so the reopen + close paths looked green in unit tests + dry-run.
- **Fix (homelab `0e163be` + `219424e`):** post the comment BEFORE the caller's
  own state flip (the reply itself reopens), route all three reply-comment sites
  (`record_failure`, `record_pass` close + pass) through a shared
  `_post_comment_tolerating_409` helper (409 = active run mid-remediation,
  non-fatal), and make the mock enforce the real state+run-state guard.
  `TestPatrolPodiumReplyContract` reproduces both bugs (proven to fail against the
  old orderings); full homelab-stack suite 732 passed. Verified live: two manual
  `infra` cycles `COMPLETED`, 409s on issues 70/71 (active pi run) tolerated,
  issue 63 closed→**stayed** `done`. Worker now `code_sha=219424e`.
- **Residual / deferred (C-0281):** `/reply` reopens to `todo` on EVERY comment,
  so below-threshold pass-recorded issues re-dispatch pi each cycle and a close
  can be clobbered back to `in_review` by an in-flight pi run (issue 62 observed
  `done`→`in_review` ~20s post-close). The reorder fix stops the workflow
  failures but not the reopen churn; durable fix = a non-reopening comment
  endpoint on podium-api (operator-gated, excluded service), deferred this
  session.
- **Resolved (C-0285, 2026-06-20, ADR-0017):** the deferred durable fix landed.
  `POST /api/issues/{id}/comment` is the append-only Comment primitive (no state
  flip, no run-state gate, never 409s, verbatim append); `add_comment` was
  repointed `_reply_path`→`_comment_path` and stamps its own `### Patrol (<ts>)`
  header, so patrol comments no longer reopen. `patrol_plane.py` logic is
  unchanged — reopen/close stay owned by the explicit `update_issue(state=…)`
  calls, so the C-0279/C-0280 `_post_comment_tolerating_409` + comment-before-flip
  ordering are now **dead insurance** (kept until the contract soaks). Deployed
  (`podium-api`/`podium-web` then worker on homelab `8a101eb`); a live docker
  patrol confirmed `/comment` POSTs (`200`, no `/reply`, no `409`) with comment
  and reopen decoupled (failure reopens via a separate `PATCH`). Pass-no-reopen
  and close-stays-done remain test-covered; not live-observed (no docker check
  passed the verification cycle). See C-0285 and
  [Operator reply](../concepts/operator-reply.md#the-comment-sibling-adr-0017).

## Related

- [ADR-0002 — generalize Symphony behind adapter seams](adr-0002-generalize-symphony.md)
- [ADR-0005 — replace Plane with Podium](adr-0005-replace-plane-with-podium.md)
- [Blocked reconciler implementation](../concepts/blocked-reconciler-implementation.md)
- [Podium tracker](../concepts/podium-tracker.md)
- [Operator reply](../concepts/operator-reply.md) — the `/reply` reopen-on-comment semantics behind C-0279–C-0281.
- Claims C-0263 / C-0264 / C-0265; first-cycle fixes C-0271–C-0275; soak regression C-0279 / C-0280 / C-0281; durable fix C-0285 (ADR-0017 `/comment`); notes on C-0014 / C-0035.
