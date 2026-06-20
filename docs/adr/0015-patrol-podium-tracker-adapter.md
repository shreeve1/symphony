---
status: proposed
relates-to: ADR-0002 (generalize Symphony behind adapter seams), ADR-0004 (role-based tracker contract), ADR-0005 (replace Plane with Podium)
context: Temporal homelab patrol workers still write findings to Plane; they must post issues to the Podium board behind a tracker-agnostic seam, with Plane preserved as a slot-in backend
decided-with: James, 2026-06-20 (grill-me design pass over homelab plans/59.md)
plan: /home/james/homelab/plans/59.md
---

# Route Temporal patrols to Podium via a tracker-agnostic ticket-writer seam

## Context

Homelab Temporal patrol workers detect infrastructure faults and file/close
tracker issues each cycle. They write to **Plane** today
(`homelab-stack/src/homelab_worker/worker.py` →
`PlaneAdapter(transport=...)`). Symphony's own backend has already moved to
**Podium** (ADR-0005), so patrol findings land on a board the rest of the
system no longer uses.

The patrol lifecycle depends on a specific contract: a deterministic
`external_id` (`stable_external_id` → `homelab-{runbook}-{sha256[:8]}`),
create-or-reopen-or-update dedup via `find_by_external_id`, domain labels,
severity→priority, Todo/Done/Blocked states, and a
`<!-- patrol-status: {...} -->` JSON marker in the description carrying
`consecutive_passes` (plus `domain`/`severity`). When a Done issue recurs it is
reopened to Todo; when enough passes accumulate the **blocked reconciler**
(`blocked_reconciler.py`, in Symphony) sweeps it from Blocked to Done.

Podium has gaps against that contract:

- `POST /api/bindings/{name}/issues` is a plain INSERT forced to `state='todo'`
  with **no `external_id`, no dedup, no labels** (`web/api/main.py:807`);
  extra fields are rejected 400.
- `priority` enum is `low|med|high|urgent` (`med`, not Plane's `medium`).
- Comments fold into one `comments_md` blob;
  `PodiumTrackerAdapter.list_comments` returns the whole blob as **one
  synthetic comment with one timestamp** (`tracker_podium.py:245`).
- The reconciler's patrol rule counts **discrete pass comments newer than the
  latest failure** (`min_pass_comments_since_fail=2`) — structurally impossible
  on Podium's single-blob/one-timestamp model, so patrol issues would never
  auto-cure on Podium.

Operator direction (2026-06-19): *"Hard cut over. But preserve plane adapter.
Make it so I can build different adapters that slot into different ticketing
systems. Mirror how plane creates tickets but inside podium. Create a separate
podium adapter."*

## Decision

Introduce a **tracker-agnostic ticket-writer seam** in the homelab repo and add
a **separate `PodiumAdapter`** as a peer of the existing `PlaneAdapter`. Hard-cut
the patrol worker to Podium behind a single `PATROL_TRACKER=podium|plane`
toggle (default `podium`). Reach **full lifecycle parity** on Podium —
create / dedup / reopen / update **and** auto-cure — not just posting.

### 1. Neutral seam (homelab)

`src/homelab_router/ticket_writer.py` already defines a `TicketWriter`
Protocol, but its method signatures still use **Plane types** (`PlaneState`,
`PlaneLabel`, `IssuePayload`). Neutralize them so a non-Plane adapter need not
speak Plane: neutral `TicketState`/`TicketDomain`/`TicketSeverity` (reused from
`patrol_models`) and a neutral `TicketWrite` payload. `PlaneAdapter` keeps all
its methods and gains thin neutral shims so it still satisfies the seam.
`patrol_plane.py` depends only on `TicketWriter` + neutral types; activity names
(`record_patrol_*`) are unchanged, so no Temporal workflow signature changes.

### 2. Separate `PodiumAdapter` (homelab)

`src/homelab_router/podium_adapter.py` + `podium_http.py` implement
`TicketWriter` over an async HTTP transport to `podium-api.service`, mirroring
`PlaneAdapter`/`PlaneHttpTransport`. Neither adapter imports the other; both are
peers behind the seam. Mapping tables: severity→priority
`{CRITICAL:urgent, HIGH:high, MEDIUM:med, LOW:low}` (note `med`); state
`{TODO:todo, DONE:done, BLOCKED:blocked}`. Domain/severity persist in the
existing `<!-- patrol-status: ... -->` marker inside `description` — **no new
columns** — so the `consecutive_passes` logic is reused verbatim.

### 3. `external_id` dedup on Podium (Symphony — excluded service)

Podium has no dedup key. Add it:

- Alembic migration: `external_id TEXT` on `issue` + a **global-unique nullable**
  index. Global (not composite with `binding_name`) because patrol ids are
  already globally collision-proof by the sha-hash scheme, and both the adapter
  and the reconciler treat `external_id` as a global key — keeping the Podium
  contract identical to Plane's `?external_id=` lookup. Nullable so existing
  rows / UI-created issues are unaffected.
- `IssueCreate`/`IssuePatch` accept and persist `external_id`.
- `GET /api/bindings/{name}/issues?external_id=...` filter (mirrors Plane).

`external_id` on the Podium row does **double duty**: adapter dedup
(`find_by_external_id`) *and* reconciler rule selection (the patrol rule keys on
`external_id_prefix="homelab-patrol-"`). Both need the column.

### 4. Cure parity — marker-trusting reconciler rule (Symphony — excluded service)

The discrete-comment-counting cure rule is dead on Podium (single-blob
comments). Add a Podium-only `patrol-passes-marker` reconciler rule that reads
the `<!-- patrol-status: ... -->` marker out of `issue["description"]` (already
`SELECT *`-ed by `list_issues_by_state`, so no extra fetch) and fires when:

> `consecutive_passes >= 2 AND last_pass_at > last_fail_at`

This requires the patrol marker to carry `last_pass_at` / `last_fail_at`
timestamps, which it does not today (`base_metadata`) — the patrol writer
(homelab) adds them.

**Trusting the marker is justified on Podium specifically.** The documented
reason the reconciler ignores `consecutive_passes` on Plane (C-0014 / C-0035)
is that Plane's rich-text editor strips HTML comments from `description_html`
on round-trip, permanently resetting the counter to 1
(`patrol_plane.py:65-71,256-261`; observed live 2026-05-18). That is an
**editor bug, not patrol logic.** Podium stores `description` as plain markdown
with no editor round-trip, so the marker survives and `consecutive_passes`
increments correctly. The Plane comment-counting rule stays the correct behavior
for the Plane backend; the marker rule is **additive**, selected by tracker.

### 5. Patrol binding — route to the existing `homelab` binding

**Revised 2026-06-20 (operator): post patrol issues to the existing `homelab`
binding, not a new `homelab-patrol` binding.** This mirrors the retired Plane
setup more faithfully (patrols posted into the homelab `automations` project,
which is the `homelab` binding's tracker) and removes the need to scaffold a new
binding or author a new `WORKFLOW.md` — the `homelab` binding is already a live
infra binding with a medium-risk autonomy `WORKFLOW.md` and `repo_path` on the
homelab repo. No collision problem: dedup queries `?external_id=` AND
`binding_name=homelab`, and the reconciler patrol rule keys on the
**external_id** prefix `homelab-patrol-` (the id, not the binding), so cure and
dedup are correctly scoped without a separate binding.

`PodiumAdapter`'s `binding` constructor arg is therefore `homelab` (set in
Wave C wiring — no change to the Wave A/B code). Dispatch posture:
**auto-dispatch all** — mirror Plane; every patrol finding auto-spawns a
remediation agent (a Todo patrol issue is dispatched like any homelab issue; a
reopen re-dispatches).

### 6. Adapter state contract (per-state collision avoidance)

The adapter mutates issue state only where safe:

- `done` → reopen to `todo` (recurrence);
- `blocked` → evidence-only, never re-state (the reconciler cures);
- `running` / `in_review` → **never touch state** (an agent or operator owns it);
- none → create.

## Build sequencing

Re-sequenced from plan 59's literal 1→4 to consolidate the one excluded-service
window and de-risk the migration:

- **Wave A (homelab, zero service impact):** neutralize the seam; add
  `last_pass_at`/`last_fail_at` to the marker; build `PodiumAdapter` +
  `PodiumHttpTransport`; unit-test against an in-memory Podium transport. No
  Symphony touch.
- **Wave B (Symphony, ONE gated window, ONE `podium-api` restart):** the
  `external_id` migration + endpoint + filter, the `patrol-passes-marker`
  reconciler rule, and the `homelab-patrol` binding — all batched so the
  excluded-service restart is paid **once**, with the adapter contract already
  proven against the mock.
- **Wave C (cutover + verify):** wire `worker.py` + `PATROL_TRACKER`; dry-run a
  patrol cycle on Podium (create / reopen / update / cure); restart the patrol
  worker.

## Considered options

- **Composite `UNIQUE(binding_name, external_id)`.** Rejected: patrol ids are
  already globally unique; composite would force a redundant binding arg on the
  `?external_id=` filter and diverge from Plane's global-key contract. Only wins
  if a second binding intentionally mints the same id — ruled out by the
  sha-hash scheme.
- **Dedicated `domain`/`severity` columns instead of the marker.** Rejected for
  now (reversible at Wave B): the marker already carries them as JSON and
  round-trips on Podium markdown; columns add migration weight for querying we
  don't need yet.
- **Tier 1 only (post + reopen, defer auto-cure).** Rejected: without the
  reconciler rule, cured patrol issues pile up in Blocked — the exact failure
  the reconciler exists to prevent, reproduced on the new board. Operator chose
  full parity.
- **Patrol worker self-closes (skip the reconciler).** Rejected: duplicates
  cure logic outside the one place that owns it and breaks the tracker-agnostic
  reconciler seam.
- **Build Wave 2 (schema) before the adapter, per plan 59's literal order.**
  Rejected: migrating the excluded service against an unproven contract risks a
  second gated restart. Adapter is built and mock-tested first.

## Consequences

- Two excluded-service changes (migration + reconciler rule) land in one
  approved, scheduled `podium-api`/`symphony-host` window — operator-gated.
- Plane remains a fully-working slot-in backend; `PATROL_TRACKER=plane` reverts.
- Cross-repo: homelab (seam, adapter, marker, cutover) and Symphony (schema,
  reconciler, binding) commit independently to their own `main`.
- The marker becomes load-bearing for cure timing on Podium (was diagnostic-only
  on Plane) — reverses the Plane-era stance **for the Podium backend only**.

## Implementation status (2026-06-20)

Waves A and B are **built, tested, committed, and inert** (nothing applied/
restarted). Wave C + the gated apply remain.

- **Wave A — homelab `e86d69d`** (`automation/homelab-stack`): `ticket_types.py`
  neutral vocabulary (moved `stable_external_id`/`CommentPayload`/`IssuePayload`,
  neutral `TicketState`/`TicketLabel`; `plane_adapter` re-exports for back-compat);
  marker gained `last_pass_at`/`last_fail_at` (injectable `_utcnow_iso`);
  `podium_adapter.py` + `podium_http.py` (`PodiumAdapter` imports only
  `ticket_types`, verified). pi audit clean; 172 targeted tests pass.
- **Wave B — symphony `44d6b5f`**: migration `0009_issue_external_id`
  (`external_id TEXT` + global-unique nullable `ix_issue_external_id`, idempotent);
  runtime-schema parity; `external_id` on `IssueCreate`/`IssuePatch` + create/PATCH
  persist + UNIQUE→409; `?external_id=` list filter; reconciler marker-first cure.
  pi audit: 0 critical, 2 warnings (migration index-skip, PATCH 409) both
  auto-fixed + covered. Full suite 966 passed.

**Revision to §4 (ratified during build):** the cure was implemented as a
**unified marker-first-with-comment-fallback inside the existing patrol rule**,
NOT a separate `patrol-passes-marker` `DEFAULT_RULES` entry. The reconciler call
site (`scheduler/__init__.py:1117`) passes no per-tracker rules, so consolidation
avoids plumbing tracker-kind through. Behavior is still tracker-scoped de facto:
the marker only survives on Podium markdown, so on Plane (editor-stripped) the
code falls through to the unchanged comment-counting path. `DEFAULT_RULES`
prefix/threshold and the Plane path are byte-for-byte preserved.

**Migration idempotency (discovered during build):** `ensure_schema` builds fresh
DBs from `SCHEMA_SQL` (already head shape, incl. `external_id`) but stamps them at
`INITIAL_REVISION` (0008), so a later `alembic upgrade head` re-runs 0009 — it
guards the `ADD COLUMN` and always `CREATE UNIQUE INDEX IF NOT EXISTS`.

**Remaining (Wave C + gated window) — updated 2026-06-20 for the existing-`homelab`-binding decision:**
- Gated `podium-api` window (operator-scheduled, excluded-service): apply
  migration 0009 to live `podium.db`; restart `podium-api.service` (loads the
  Wave B endpoint code). For the cure half of parity also restart
  `symphony-host.service` (loads the marker-first reconciler). **No new binding
  to scaffold and no new `WORKFLOW.md`** — patrols target the existing `homelab`
  binding.
- Wave C (homelab, low impact): wire `worker.py` → `PodiumAdapter(binding="homelab")`,
  `PATROL_TRACKER=podium|plane` toggle, patrol-worker host config (Podium base
  URL + token + `binding=homelab`); then dry-run a patrol cycle on Podium and
  restart the patrol worker. Live dry-run depends on the gated window above.
