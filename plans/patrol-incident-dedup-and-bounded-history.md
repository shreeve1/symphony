# Plan: Patrol incident deduplication and bounded history

## Task Description

Implement the cross-repository patrol incident contract defined in
`PRDs/patrol-incident-dedup-and-bounded-history.md`. Replace exact-alert
recurrence with deterministic Incident identity (`incident_family` +
`incident_resource`), coalesce simultaneous threshold findings, and apply an
atomic Podium recurrence policy that suppresses unchanged redispatch and comment
growth. Bound patrol audit history and native agent continuity to three Runs,
make Archive sever active identity while preserving historical metadata, and
leave operator/coding issues unchanged.

This spans two repositories:

- Symphony owns the Podium transaction, archive semantics, Run retention,
  dispatch/session accounting, and scheduler integration.
- Homelab owns finding normalization, Incident coalescing, alert-rule identity
  labels, the Podium adapter request, and Temporal workflow outcome counters.

The two repositories must be committed and deployed independently in the order
specified below. Do not edit or pause `schedule-alert-forwarder` as part of this
work.

## Objective

Deliver one active Podium issue and at most one active agent Run per patrol
Incident. Repeated unchanged evidence must replace current Incident state and
increment visibility metadata without appending comments, moving the issue to
Todo, or dispatching an agent. First detection, a genuine severity escalation,
a Done recurrence, or an operator reply may dispatch. Archive must atomically
release the active dedup key so a later recurrence receives a new issue and a
fresh session. Only the newest three patrol Run rows/logs and the matching
three-Run native-session generation may remain in scope; non-patrol behavior
must remain byte-for-byte compatible.

## Problem Statement

The live path currently keys alert-forwarder findings by alert name and
Alertmanager series fingerprint. Related threshold rules such as
`HostDiskUsageHigh` and `HostDiskUsageCritical` therefore create separate issues
for the same host/mountpoint. Independently, `record_failure` appends a comment,
PATCHes every existing issue back to Todo, and causes the scheduler to dispatch
again even when evidence and severity are unchanged. One live issue exceeded
hundreds of Runs, tens of millions of input tokens, and hundreds of thousands of
comment characters.

Deleting old Run rows alone cannot fix the cost: comments and the issue-scoped
native CLI session are separate prompt inputs. Conversely, suppressing dispatch
without a durable current-evidence view would leave the issue stale. The change
must therefore coordinate identity, recurrence, comments, Run retention, and
session rotation while preserving current scheduling, operator reply, and
recovery behavior.

## Solution Approach

1. Add a pure homelab `incident_coalescer` that groups normalized findings by an
   explicit `(incident_family, incident_resource)` tuple, picks the highest
   severity deterministically, and retains sibling evidence. Missing identity
   falls back conservatively to the existing alert/check identity plus per-series
   fingerprint; uncertainty always separates findings.
2. Add a pure Symphony `patrol_incident` recurrence-policy module and a dedicated
   `POST /api/bindings/{name}/incidents/observe` endpoint. The endpoint computes
   the deterministic external key and applies create, silent update, queued
   escalation, dispatch release, Done reopen, pass confirmation, or recovery in
   one explicit `BEGIN IMMEDIATE` SQLite transaction. The handler must begin
   before its first read, commit only after read/decide/write, and roll back every
   exception; a two-connection concurrency test establishes this new repository
   transaction precedent. Lookup first uses active family/resource, then the
   observation's bounded list of exact legacy external ids, so the first
   new-format observation can adopt an existing row without rewriting its key or
   creating a new duplicate. Client-side GET-then-PATCH is not the authority
   because concurrent Temporal workflows could duplicate escalation comments or
   dispatch transitions.
3. Persist patrol-only machine state in nullable/defaulted Issue columns:
   family/resource, first/last seen, occurrence count, current severity,
   last-dispatched severity, pending severity, consecutive passes, and dispatch
   count. Persist the actual generated session id on each Run. Continue rendering
   current evidence plus durable Incident metadata into `description` so the
   operator and a fresh agent session can inspect bounded current state.
4. Treat a patrol archive as a lineage boundary: in the same PATCH transaction,
   set `state='archived'` and `external_id=NULL`, while retaining Incident columns
   and the description marker. Exempt archived patrol issues from the existing
   14-day hard purge; non-patrol archive retention remains unchanged. Done keeps
   the key and recurrence reopens the same issue.
5. On actual patrol Run creation, increment the durable dispatch count, copy
   current severity to last-dispatched severity, and persist the generated
   session id. Use session generation `dispatch_count // 3` before increment, so
   Runs 1–3 share generation 0, Run 4 starts generation 1, and later Runs within
   that generation resume normally. Backfill existing patrol dispatch counts
   from Run rows before pruning.
6. Add patrol-only retention that protects queued/running Runs, keeps the newest
   three completed Runs/logs, deletes older logs and rows, and never leaves
   `issue.latest_run_id` pointing to a deleted row. Run it after terminal Run
   updates and from startup/periodic reconciliation so existing oversized issues
   are cleaned. Preserve the existing 90-day/100-log, row-preserving behavior for
   non-patrol issues.
7. Expose low-cardinality structured actions/counters (`created`, `coalesced`,
   `silent_update`, `escalated`, `archive_severed`, `pruned_rows`,
   `pruned_logs`) in API/worker results and logs. Never log diagnostic bodies or
   secrets.

## Relevant Files

Use these files to complete the task:

### Symphony

- `web/api/schema.py` — add patrol Incident state, dispatch count, and Run session
  id columns; advance the schema revision.
- `web/api/main.py` — add the atomic Incident observation endpoint, include
  Incident fields in issue projections, sever patrol identity on Archive, resolve
  session-tail paths from the active Run's persisted session id, and exempt
  archived patrol issues from the general 14-day purge.
- `tracker_podium.py` — persist patrol dispatch/session metadata on Run creation,
  add patrol row/log pruning, and preserve the latest-Run projection.
- `session_continuity.py` — derive deterministic generation-scoped patrol session
  ids while preserving the current operator issue id contract.
- `scheduler/__init__.py` — choose the patrol session generation from the durable
  dispatch count and pass the resulting id through existing resume/refeed logic.
- `scheduler/run_records.py` — include the candidate's generated session id in
  the explicit Run payload passed to the tracker.
- `scheduler/reconcile.py` — invoke and log patrol row retention independently of
  the existing general log-only retention pass.
- `web/api/tests/test_issue_patch.py` — verify Archive releases only patrol
  identity atomically while Done and non-patrol semantics are unchanged.
- `web/api/tests/test_archive_purge.py` — prove archived patrol metadata survives
  the general purge while existing non-patrol purge behavior remains.
- `web/api/tests/test_alembic_baseline.py` — verify migration/backfill and runtime
  schema parity.
- `web/api/tests/test_session_tail.py` — verify generated patrol session ids are
  used for local live tailing, with legacy fallback for null ids.
- `tests/test_tracker_podium.py` — verify patrol dispatch count/session persistence
  and latest-Run projection behavior.
- `tests/test_log_retention.py` — verify patrol row/log cap, active-Run protection,
  immediate and reconciliation cleanup, and non-patrol compatibility.
- `tests/test_session_continuity.py` — verify three-Run generation boundaries and
  unchanged legacy session derivation.
- `tests/test_scheduler.py` — verify Run 4 re-feeds into a fresh session, Runs 2–3
  resume, and patrol severity is marked dispatched only when a Run is created.

### Homelab (separate repository)

- `/home/james/homelab/automation/homelab-stack/src/homelab_worker/patrol_models.py`
  — add optional Incident family/resource and sibling-evidence fields to normalized
  findings without changing Temporal-safe primitive serialization.
- `/home/james/homelab/automation/homelab-stack/src/homelab_worker/patrol_workflow.py`
  — coalesce the result batch before ticket activities and report action counts.
- `/home/james/homelab/automation/homelab-stack/src/homelab_worker/alert_forwarder.py`
  — parse Incident labels, coalesce a poll, compare close-by-absence by Incident
  identity, and preserve Watchdog behavior.
- `/home/james/homelab/automation/homelab-stack/src/homelab_worker/patrol_plane.py`
  — route Podium observations through the new atomic endpoint and retain the
  existing Plane path as the legacy fallback.
- `/home/james/homelab/automation/homelab-stack/src/homelab_router/ticket_types.py`
  — define neutral Incident observation/outcome DTOs used across the worker and
  Podium adapter.
- `/home/james/homelab/automation/homelab-stack/src/homelab_router/ticket_writer.py`
  — extend the tracker-neutral seam with an Incident observation operation.
- `/home/james/homelab/automation/homelab-stack/src/homelab_router/podium_adapter.py`
  — call the Incident observation endpoint, expose its action/result, filter
  archived rows from forwarder reconciliation, and stop unchanged observations
  from using `/comment` or generic state PATCHes.
- `/home/james/homelab/automation/homelab-stack/src/homelab_router/plane_adapter.py`
  — preserve the dormant Plane backend's existing exact-id behavior under the
  extended ticket-writing contract.
- `/home/james/homelab/automation/homelab-stack/deploy/monitoring/prometheus/rules/host-alerts.yml`
  — annotate warning/critical disk rules with the same family and a resource
  templated from stable instance + mountpoint dimensions.
- `/home/james/homelab/automation/homelab-stack/tests/test_patrol_models.py` —
  verify Incident metadata normalization and Temporal-safe defaults.
- `/home/james/homelab/automation/homelab-stack/tests/test_patrol_workflow.py` —
  verify native patrol batches coalesce before recording and expose counts.
- `/home/james/homelab/automation/homelab-stack/tests/test_alert_forwarder.py` —
  verify threshold coalescing, distinct resources, fallback identity,
  close-by-absence, and unchanged Watchdog semantics.
- `/home/james/homelab/automation/homelab-stack/tests/test_patrol_plane.py` —
  verify Podium observation routing, recovery thresholds, and unchanged Plane
  fallback behavior.
- `/home/james/homelab/automation/homelab-stack/tests/test_podium_adapter.py` —
  verify request/response mapping and that silent updates emit no comment or Todo
  PATCH.

### New Files

- `patrol_incident.py` — pure Incident identity, severity rank, and recurrence
  decision module.
- `tests/test_patrol_incident.py` — table-driven recurrence matrix and identity
  tests.
- `web/api/migrations/versions/0021_patrol_incident_history.py` — additive schema,
  existing-patrol backfill, and dispatch-count initialization.
- `web/api/tests/test_patrol_incidents.py` — atomic observation endpoint and
  concurrency contract tests.
- `/home/james/homelab/automation/homelab-stack/src/homelab_worker/incident_coalescer.py`
  — pure deterministic coalescer.
- `/home/james/homelab/automation/homelab-stack/tests/test_incident_coalescer.py`
  — table-driven identity, severity, tie-break, and shuffled-order tests.

## Implementation Phases

### Phase 1: Foundation

Land pure identity/policy contracts and the Symphony migration. Backfill patrol
state without changing issue ids or states: preserve existing `external_id`,
derive conservative legacy family/resource from stored marker data where
possible, initialize occurrence metadata, set `patrol_dispatch_count` from the
pre-prune Run count, and leave ambiguous legacy rows separated. This phase is
inert until the new observation endpoint and homelab caller are deployed.

### Phase 2: Core Implementation

Add the atomic Podium observation endpoint, archive lineage boundary, homelab
coalescer, and adapter/workflow routing. Deploy Symphony API/migration before the
homelab worker so the caller never targets a missing route. Keep the alert
forwarder schedule running and preserve scheduled-hold and operator-reply
semantics.

### Phase 3: Integration & Polish

Add immediate plus reconciliation Run retention, session generation rotation,
structured counters, full regression coverage, and controlled live verification.
Deploy/restart in dependency order, observe one disposable disk-resource pair,
and roll back the homelab caller first if the endpoint contract fails.

## Step by Step Tasks
IMPORTANT: Execute every step in order when running manually. `/dev-build` will parallelize independent groups automatically.

### 1. Define pure Incident contracts [parallel-safe]
- [x] [1.1] Create `patrol_incident.py` with canonical severity values/ranks,
  deterministic family/resource key derivation, typed recurrence inputs/actions,
  and a pure decision function covering create-and-dispatch, silent update,
  queued escalation, escalation release, Done reopen, pass confirmation, and
  recovery. Treat scheduled holds and queued/running Runs as dispatch barriers;
  never inspect titles or diagnostics for identity.
- [x] [1.2] Create
  `/home/james/homelab/automation/homelab-stack/src/homelab_worker/incident_coalescer.py`
  with a pure grouping function. Highest severity wins; equal-severity ties use a
  stable key independent of input order; sibling evidence and each member's exact
  legacy external id are sorted, bounded, and retained; missing family/resource
  falls back to exact check/alert plus series fingerprint (then instance/check
  name), never to a broader resource.
- [x] [1.3] Update
  `/home/james/homelab/automation/homelab-stack/src/homelab_worker/patrol_models.py`
  so `CheckResult` carries optional `incident_family`, `incident_resource`, and
  bounded sibling evidence using Temporal-safe primitives. Preserve current
  external-id behavior when both explicit fields are absent.
- [x] [1.4] Update
  `/home/james/homelab/automation/homelab-stack/src/homelab_router/ticket_types.py`
  with neutral `IncidentObservation` and `IncidentWriteOutcome` DTOs, including a
  bounded `legacy_external_ids` tuple for cutover adoption; diagnostics remain
  redacted/truncated before crossing the HTTP boundary.

### 2. Add and backfill Podium Incident persistence [sequential]
- [x] [2.1] Create
  `web/api/migrations/versions/0021_patrol_incident_history.py` and update
  `web/api/schema.py` with patrol-only Issue columns for family/resource,
  first/last seen, occurrence count, current severity, last-dispatched severity,
  pending severity, consecutive passes, and dispatch count, plus
  `run.agent_session_id`. Keep defaults/nullability safe for operator issues and
  constrain severity values to the canonical order.
- [x] [2.2] In
  `web/api/migrations/versions/0021_patrol_incident_history.py`, backfill
  `patrol_dispatch_count` from all persisted existing Run rows before any pruning
  (startup reconciliation will terminalize orphaned queued rows). Recover
  explicit legacy identity only from valid `patrol-status` marker fields; when
  family/resource is absent, preserve exact external-id separation rather than
  guessing or merging historical duplicates. Populate old Run session ids with
  the legacy issue-derived id only where safe; a null remains an explicit legacy
  fallback.
- [x] [2.3] Update `web/api/main.py` issue SELECT/decoration paths and create
  defaults so Incident fields round-trip without changing operator-created issue
  payloads or UI behavior.

### 3. Implement atomic recurrence handling [sequential]
- [x] [3.1] In `web/api/main.py`, add a validated
  `POST /api/bindings/{name}/incidents/observe` payload and call the pure
  `patrol_incident.py` policy inside one explicit transaction: execute
  `BEGIN IMMEDIATE` before the first lookup, perform read/decide/write on that
  connection, commit once, and roll back on every exception. Compute the active
  external key server-side from family/resource; after acquiring the write lock,
  look up an active row by family/resource first, then by any exact
  `legacy_external_ids` supplied by the canonical coalesced finding. Adopt a
  legacy match by populating Incident columns while preserving its external id;
  create with the new key only when neither lookup matches. If multiple legacy
  rows already exist, choose the highest-severity/newest deterministic canonical
  row but do not merge/delete the others (historical duplicate merge is out of
  scope). Cover busy/uniqueness failures with clean rollback rather than asking
  the client to retry a GET/PATCH sequence.
- [x] [3.2] In `web/api/main.py`, implement action writes: first detection inserts
  one patrol Todo; silent recurrence replaces description/title/priority/current
  evidence and increments `last_seen_at`/occurrence count without touching
  comments/state/schedule; escalation sets pending severity and only moves to Todo
  when no Run or schedule hold blocks dispatch; Done recurrence reopens the same
  row; confirmed recovery appends one concise event and closes only when no Run is
  active. Copy lower-severity sibling evidence into the current description, not
  separate issues/comments.
- [x] [3.3] In `web/api/main.py`, append comments only when the policy returns
  first detection, released escalation, Done recurrence, or confirmed recovery.
  Return a stable action enum and counters, publish one `issue.updated` event, and
  touch the wake sentinel only for actions that actually make Todo dispatchable.
  Emit low-cardinality structured logs without diagnostic text.
- [x] [3.4] In `tests/test_patrol_incident.py`, cover the full state/severity/run
  matrix (`todo`, `running`, `in_review`, `blocked`, `done`, `archived`; unchanged,
  escalation, lower severity, recovery; active/inactive; scheduled hold), including
  comparison to last-dispatched rather than latest-observed severity.
- [x] [3.5] In `web/api/tests/test_patrol_incidents.py`, prove atomic first create,
  silent updates, one queued/released escalation, and no duplicate escalation
  under concurrent observations from two independent SQLite connections/threads.
  Also cover rollback after policy/write failure, Done same-id reopen, distinct
  resources, conservative fallback, legacy-id adoption without new duplication,
  deterministic choice among pre-existing duplicate rows, recovery comment
  idempotency, valid websocket/wake behavior, and no diagnostic leakage in logs.

### 4. Make Archive the patrol lineage boundary [parallel-safe]
- [x] [4.1] Update `web/api/main.py` `patch_issue` so a transition of an
  `origin='patrol'` row to `archived` includes `external_id=NULL` in the same SQL
  transaction as the state change. Retain Incident columns and description;
  restoring the archived row later must not silently reclaim the released key.
  Done and non-patrol transitions remain unchanged.
- [x] [4.2] Update `web/api/main.py` archived purge selection to exclude patrol
  issues, preserving archived Incident metadata while leaving the current 14-day
  non-patrol purge contract intact.
- [x] [4.3] Extend `web/api/tests/test_issue_patch.py` with atomic release,
  recurrence-after-Archive new-id, Done recurrence same-id, and uniqueness rollback
  coverage. Extend `web/api/tests/test_archive_purge.py` to retain old patrol
  archives and still purge old operator/coding archives.

### 5. Route coalesced homelab findings [sequential]
- [ ] [5.1] Update
  `/home/james/homelab/automation/homelab-stack/deploy/monitoring/prometheus/rules/host-alerts.yml`
  so `HostDiskUsageHigh` and `HostDiskUsageCritical` share an explicit disk-usage
  family and derive the resource from instance plus mountpoint. Do not change
  thresholds, durations, or the alert-forwarder schedule.
- [ ] [5.2] Update
  `/home/james/homelab/automation/homelab-stack/src/homelab_worker/alert_forwarder.py`
  to parse the new labels, coalesce each poll before recording, and compare the
  close-by-absence set using Incident identity. Preserve Watchdog's close-nothing
  gate and exact per-series fallback for unannotated alerts.
- [ ] [5.3] Update
  `/home/james/homelab/automation/homelab-stack/src/homelab_worker/patrol_workflow.py`
  to call the pure coalescer immediately after `run_patrol_checks`, compute
  `PatrolRunSummary` from the original batch, then iterate canonical findings
  (not original results) for ticket activities. Compute Incident action counters
  from canonical outputs so the workflow's N-results-to-one-observation change is
  explicit and deterministic.
- [ ] [5.4] Update
  `/home/james/homelab/automation/homelab-stack/src/homelab_router/podium_adapter.py`
  to post `IncidentObservation` to the new endpoint and map its stable action
  response. Filter both `done` and `archived` from open forwarder reconciliation.
  An action of `silent_update` must perform no `/comment`, `/reply`, or generic
  state PATCH.
- [ ] [5.5] Extend
  `/home/james/homelab/automation/homelab-stack/src/homelab_router/ticket_writer.py`
  with `observe_incident`, implement it in `podium_adapter.py`, and update
  `/home/james/homelab/automation/homelab-stack/src/homelab_worker/patrol_plane.py`
  to route fail/warning/pass results through that tracker-neutral operation,
  including configured recovery confirmation. Do not import or type-check the
  concrete Podium adapter in worker logic.
- [ ] [5.6] Update
  `/home/james/homelab/automation/homelab-stack/src/homelab_router/plane_adapter.py`
  with a compatibility `observe_incident` implementation that delegates to its
  existing exact-id create/update/pass behavior; do not implement semantic family
  coalescing or change Plane state/comment behavior.

### 6. Bound patrol Run rows and logs [sequential]
- [ ] [6.1] Add `PodiumTrackerAdapter.prune_patrol_runs` in
  `tracker_podium.py`. Scope by `issue.origin='patrol'`; retain all queued/running
  rows plus the newest three completed rows ordered by Run id; unlink older logs
  best-effort and delete their rows FK-safely. Repair `latest_run_id`,
  `latest_run_state`, and `latest_verdict` from the newest surviving Run only if
  the deleted set could invalidate the projection.
- [ ] [6.2] In `tracker_podium.py`, invoke issue-scoped patrol pruning after a Run
  becomes terminal. Keep `prune_run_logs`' existing non-patrol row-preserving
  90-day/100-log behavior unchanged.
- [ ] [6.3] Update `scheduler/reconcile.py` to call patrol pruning at startup and
  on the existing daily retention cadence, logging separate row/log counts so
  legacy oversized patrol issues are cleaned even without another Run.
- [ ] [6.4] Extend `tests/test_log_retention.py` with more than three patrol Runs,
  queued/running protection, missing log files, latest projection integrity,
  archived patrol cleanup, idempotency, and non-patrol controls. Extend
  `tests/test_tracker_podium.py` for terminal-triggered pruning and rollback on FK
  failure.

### 7. Rotate patrol native sessions every three dispatches [sequential]
- [ ] [7.1] Extend `session_continuity.py` with an optional generation component in
  `derive_session_id`; generation 0 must preserve the existing UUID for all
  non-patrol issues, while patrol generations greater than 0 produce stable,
  distinct ids.
- [ ] [7.2] Update `scheduler/__init__.py` candidate preparation to read
  `patrol_dispatch_count`, derive generation `count // 3` before Run creation,
  and use that id throughout resume eligibility and agent launch. A generation
  change must select re-feed, not probe/resume the older file.
- [ ] [7.3] Update `scheduler/run_records.py` to add
  `agent_session_id` to the explicit start-Run payload, and update
  `tracker_podium.py`'s INSERT SQL plus `_RUN_INSERT_COLUMNS` to persist it.
  Explicitly exclude the immutable session id from `_RUN_UPDATE_COLUMNS`. In the
  same `record_run` transaction, issue an `UPDATE ... WHERE id = ? AND
  origin = 'patrol'` to increment dispatch count, copy current severity into
  last-dispatched severity, and clear a satisfied pending escalation; zero rows
  is the expected non-patrol case. Dispatch-gate or prompt-render failures before
  Run creation must not increment the counter.
- [ ] [7.4] Update `web/api/main.py` `_SessionTailer` running-Run SELECT to include
  `r.agent_session_id` and use it for the local session path; retain
  `derive_session_id(issue_id)` only as a legacy null fallback. Do not change
  remote spool tailing.
- [ ] [7.5] Extend `tests/test_session_continuity.py`, `tests/test_scheduler.py`,
  `tests/test_tracker_podium.py`, and `web/api/tests/test_session_tail.py` to prove
  Runs 1–3 share/resume generation 0, Run 4 uses a fresh full prompt/session,
  Runs 5–6 resume generation 1, pruning does not reset the generation, and
  operator/non-patrol continuity is unchanged.

### 8. Complete migration and cross-repo regression coverage [parallel-safe]
- [x] [8.1] Extend `web/api/tests/test_alembic_baseline.py` to upgrade from 0020,
  verify every new column/index/check, backfill an oversized patrol issue's full
  pre-prune dispatch count, leave operator rows at defaults, and match
  `SCHEMA_SQL` exactly.
- [ ] [8.2] Create
  `/home/james/homelab/automation/homelab-stack/tests/test_incident_coalescer.py`
  with warning+critical same-resource, equal-severity tie, distinct host,
  distinct mountpoint, distinct family, shuffled input, missing one/both identity
  labels, and bounded sibling-evidence cases.
- [ ] [8.3] Extend
  `/home/james/homelab/automation/homelab-stack/tests/test_patrol_models.py` and
  `/home/james/homelab/automation/homelab-stack/tests/test_patrol_workflow.py`
  for serialization defaults, canonical action counts, and original health totals.
- [ ] [8.4] Extend
  `/home/james/homelab/automation/homelab-stack/tests/test_alert_forwarder.py`
  with mocked dual disk thresholds producing one canonical issue, distinct
  resources producing separate issues, safe unannotated fallback, silent repeated
  polls, one escalation, one recovery, and unchanged Watchdog/close-by-absence
  behavior.
- [ ] [8.5] Extend
  `/home/james/homelab/automation/homelab-stack/tests/test_patrol_plane.py` and
  `/home/james/homelab/automation/homelab-stack/tests/test_podium_adapter.py` for
  endpoint mapping, no-comment/no-Todo silent updates, queued escalation, recovery
  confirmation, Archive absence from reconciliation, and Plane compatibility.

### 9. Validate and roll out in dependency order [sequential]
- [ ] [9.1] Run the targeted and full Symphony suites named under `## Validation
  Commands`; verify migration parity and that no non-patrol retention/session/API
  test changes behavior.
- [ ] [9.2] Run the targeted and full homelab-stack suites named under
  `## Validation Commands`; validate `host-alerts.yml` with the repository's
  existing Prometheus/rule tests. Commit each repository separately without
  staging either repository's pre-existing unrelated changes.
- [ ] [9.3] Apply migration 0021 and restart `podium-api.service` before deploying
  the homelab worker; the additive schema and old create/PATCH routes must remain
  backward compatible while no new caller exists. Restart `symphony-host.service`
  for scheduler/retention code, then replace the Temporal patrol worker between
  polls so no old-code activity can append/comment after a new-code observation.
  The first new observation sends the coalesced members' old exact ids; the API
  adopts a matching active legacy row before considering a new-key INSERT, so
  cutover does not manufacture a duplicate solely because key formats differ.
  Drain or let any in-flight old activity finish before accepting the first new
  observation; do not add a patrol rejection gate to the shared create endpoint.
  Keep `schedule-alert-forwarder` enabled throughout.
- [ ] [9.4] On one disposable filesystem/resource, verify warning+critical produce
  one issue and one initial Run; repeated unchanged polls change only current
  evidence/last-seen/count; escalation produces one additional non-concurrent
  Run; recovery produces one event; Done reopens the same id; Archive releases
  the key and the next recurrence creates a new id/session.
- [ ] [9.5] Verify existing patrol issues retain at most three completed Run rows
  and logs, active Runs survive, latest-run projections resolve, generation 4
  starts a fresh session, structured counters increase, and no diagnostics or
  secrets appear in logs. Compare issue count, Run count, comment growth, and
  token usage before/after; roll back the homelab caller first if any invariant
  fails.

## Testing Strategy

- **Pure unit tests:** table-drive `patrol_incident.py` and homelab
  `incident_coalescer.py`; cover every state/severity/active-run branch and every
  conservative identity boundary. The repositories use `tests/` rather than a
  `tests/unit/` subtree, so keep tests in their existing locations.
- **API/integration tests:** use FastAPI's existing test client and temporary
  SQLite databases under `web/api/tests/` to verify serialized observation
  transactions, archive atomicity, migration parity, websocket/wake effects,
  concurrent observations, and retention foreign-key integrity.
- **Scheduler/continuity tests:** use the existing fake adapter/agent patterns in
  `tests/test_scheduler.py`, `tests/test_tracker_podium.py`, and
  `tests/test_session_continuity.py` to prove dispatch accounting and generation
  boundaries without launching real agents.
- **Temporal workflow tests:** extend homelab's time-skipping Temporal tests for
  end-to-end finding → coalescer → observation outcome behavior. These are the
  relevant E2E tests; no browser-facing behavior changes, so no Playwright test
  is required.
- **Regression boundaries:** operator-created and coding issues retain all Run
  rows and current session ids; non-patrol logs retain the 90-day/100-log policy;
  Plane retains exact-id legacy behavior; Watchdog still prevents false close;
  schedules are not paused or cleared by recurrence.
- **Live verification:** use controlled alert thresholds on a disposable
  resource and record only counts/ids/timestamps/token totals, never raw secret
  diagnostics.

## Tests

### T.1. Identity and coalescing
- [ ] [T.1.1] Same disk family/resource at medium+critical yields one critical
  canonical finding with medium evidence retained.
- [ ] [T.1.2] Distinct hosts, mountpoints, and families remain distinct; missing
  identity falls back to exact per-series identity.
- [ ] [T.1.3] Equal-severity and shuffled inputs produce byte-stable canonical
  output.

### T.2. Recurrence and comments
- [ ] [T.2.1] First observation creates Todo and permits one dispatch.
- [ ] [T.2.2] Unchanged active-state recurrence updates evidence/last-seen/count
  but leaves state, comments, wake sentinel, and Run count unchanged.
- [ ] [T.2.3] Escalation dispatches once when idle and remains one pending action
  while queued/running; lower/de-escalated observations do not create extra Runs.
- [ ] [T.2.4] Operator Reply retains the existing explicit redispatch behavior.
- [ ] [T.2.5] Confirmed recovery appends one concise event; routine passes remain
  silent and Watchdog failure closes nothing.

### T.3. Done, Archive, and historical lineage
- [ ] [T.3.1] Done recurrence reopens the same issue and key.
- [ ] [T.3.2] Archive clears the active key atomically, preserves metadata, and
  causes recurrence to create a different issue/session.
- [ ] [T.3.3] Old patrol archives survive general purge; old non-patrol archives
  still purge under the existing policy.

### T.4. Run retention and projections
- [ ] [T.4.1] More than three completed patrol Runs leaves exactly the newest
  three rows/logs after terminal and periodic cleanup.
- [ ] [T.4.2] Queued/running Runs are never deleted; cleanup after completion
  converges to three.
- [ ] [T.4.3] `latest_run_id` and derived state/verdict always reference the
  newest surviving Run; FK failures roll back safely.
- [ ] [T.4.4] Non-patrol rows remain and their old/excess logs follow the existing
  90-day/100-log policy.

### T.5. Session continuity
- [ ] [T.5.1] Patrol Runs 1–3 use generation 0, Run 4 starts a fresh generation 1
  session with current issue evidence, and Runs 5–6 may resume generation 1.
- [ ] [T.5.2] Pruning rows never resets dispatch count or reattaches an older
  generation.
- [ ] [T.5.3] Session Tail resolves the persisted active Run id and legacy null
  rows fall back safely; remote spool behavior is unchanged.
- [ ] [T.5.4] Operator/coding session ids and resume eligibility are unchanged.

### T.6. Migration, workflow, and observability
- [ ] [T.6.1] Migration 0021 backfills dispatch counts before pruning, preserves
  issue identity/state, separates ambiguous legacy findings, and matches the
  fresh schema.
- [ ] [T.6.2] Alert-forwarder and native patrol Temporal workflows expose created,
  coalesced, silent-update, escalation, recovery, and prune counts without
  diagnostic payloads.
- [ ] [T.6.3] Full Symphony and homelab suites pass; controlled live verification
  confirms one canonical issue, bounded Runs/comments/sessions, Done reuse, and
  Archive renewal while the forwarder schedule remains enabled.

## Progress
**Phase Status:**
- Build: `pending`
- Test: `pending`

**Task Counts:**
- Implementation: `0/40` tasks complete
- Tests: `0/22` tests passing

**Last Updated:** `---`

## Acceptance Criteria

- Explicit `(incident_family, incident_resource)` identity is deterministic;
  unannotated findings retain exact per-series separation; no fuzzy/LLM matching
  exists.
- Related warning/critical disk thresholds for one host/mountpoint create one
  issue whose title/priority follows the highest severity and whose description
  retains lower-severity evidence.
- Unchanged recurrence replaces current evidence and increments last-seen/count
  without comment append, state transition, wake, or agent Run.
- First detection, released severity escalation, Done recurrence, and operator
  reply are the only dispatch-enabling paths; one Incident never has concurrent
  Runs.
- Severity compares against the last severity whose Run was actually created;
  repeated observations during an active Run coalesce into at most one pending
  escalation.
- Recovery records exactly one concise event after confirmation; ordinary pass
  polls remain silent.
- Done retains active identity and reopens the same issue. Archive atomically
  clears the active key, retains historical Incident metadata indefinitely, and
  causes the next recurrence to create a new issue and session.
- Every patrol issue retains only its newest three completed Run rows/logs, plus
  any currently queued/running rows. Existing oversized patrol issues are cleaned
  and `latest_run_id` always remains valid.
- Non-patrol Run rows, log retention, archive purge, recurrence, comments, and
  session continuity remain unchanged.
- Patrol native session history never crosses a three-dispatch generation; a
  rotated session receives current issue description and the existing bounded
  fresh-prompt comment view.
- Structured outcomes/counts exist for created, coalesced, silently updated,
  escalated, archive-severed, pruned rows, and pruned logs without raw diagnostics
  or secrets.
- Alert-forwarder Watchdog, close-by-absence, scheduling holds, recovery
  confirmation, and operator Reply remain operational; the forwarder schedule is
  never paused by this rollout.
- Targeted and full test suites pass in both repositories, followed by controlled
  live evidence of one issue, one initial Run, silent repeats, one escalation
  Run, Done reuse, and Archive renewal.

## Testing Promise

All pure policy/coalescer matrices, Podium API/migration/retention integration
tests, scheduler/session regressions, and homelab Temporal workflow tests pass in
both repositories; controlled live verification demonstrates bounded issue,
comment, Run, log, and session growth without changing non-patrol behavior.

## Validation Commands
Execute these commands to validate the task is complete:

- `uv run pytest tests/test_patrol_incident.py tests/test_tracker_podium.py tests/test_log_retention.py tests/test_session_continuity.py tests/test_scheduler.py web/api/tests/test_patrol_incidents.py web/api/tests/test_issue_patch.py web/api/tests/test_archive_purge.py web/api/tests/test_alembic_baseline.py web/api/tests/test_session_tail.py -q` — run targeted Symphony policy/API/retention/session coverage.
- `uv run pytest -q` — run the complete Symphony regression suite.
- `cd /home/james/homelab/automation/homelab-stack && uv run pytest tests/test_incident_coalescer.py tests/test_patrol_models.py tests/test_patrol_workflow.py tests/test_alert_forwarder.py tests/test_patrol_plane.py tests/test_podium_adapter.py -q` — run targeted homelab coalescer/Temporal/adapter coverage.
- `cd /home/james/homelab/automation/homelab-stack && uv run pytest -q` — run the complete homelab-stack regression suite.

## Notes

- This is a complex cross-repository build. Use `/to-issues` so Symphony schema,
  API, homelab coalescing, retention, session rotation, and live rollout can land
  as dependency-ordered vertical slices rather than one oversized session.
- Symphony's migration/API must deploy before the homelab caller. The homelab
  worker is the first rollback point; migration columns are additive and may
  remain inert during rollback.
- Existing patrol duplicate rows are not merged, historical comments are not
  rewritten, and alert thresholds/remediation logic are unchanged. The adoption
  lookup prevents new cutover duplicates but intentionally leaves duplicate rows
  that already existed before this feature for separate operator cleanup.
- The current 12,000-character fresh-prompt comment cap remains defense in depth;
  recurrence suppression and session generation provide the primary token bound.
- `BEGIN IMMEDIATE` is intentionally a new Podium endpoint pattern. Keep its
  lock scope to one Incident row decision, rely on the configured SQLite busy
  timeout, and prove commit/rollback behavior with two-connection tests before
  reusing it elsewhere.
- Coordinate homelab edits with the concurrent alert-forwarder work and never
  stage its unrelated dirty files.
- Podium slice exemption applies: do not edit `wiki/` during implementation
  slices; capture rationale in issue comments and run one consolidated wiki update
  after the batch lands.
