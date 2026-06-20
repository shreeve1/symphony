# Session Capture: ADR-0018 grill — patrol medium-risk updates self-schedule into the maintenance window

- Date: 2026-06-20
- Purpose: Review what's outstanding between Temporal patrols and Podium after the ADR-0015 cutover; decide how medium-risk patrol findings should actually get applied.
- Method: `/grill-me` over the live system (read-only DB/journal inspection + codebase), then three decision questions.

## Durable Facts (verified this session)

- **Patrols→Podium is healthy and live.** Live `podium.db` (22:27 UTC) shows the
  `homelab` binding actively receiving findings: issue 69 (pihole) ran the full
  auto-cure path (`pass → closed after 2 consecutive passes`), issue 62 (aidev
  disk) auto-remediated (86%→79%) and closed. The reopen-churn bug is fixed via
  the `/comment` primitive (ADR-0017). — Evidence: `podium.db` issues 62–76;
  comments_md tails.
- **Medium-risk findings correctly BLOCK awaiting a maintenance window.** Live
  blocked issues are agents refusing to apply without authorization, not failures:
  71 (ita-n8n: reboot needs current-window auth + active sessions present), 66
  (pve3: "runbook says patrol must not apply updates directly; no current schedule
  context or James approval"), 74 (aidev: dockerops runbook requires operator
  approval before prune). — Evidence: `comments_md` tails of issues 66/71/74.
- **The detection cron never runs inside the window.** Patrol crons (UTC,
  `patrol_config.py:414`): security `30 1,13`, **infra `0 3,15`** (=8pm/8am LA),
  network `30 4,16`, media `0 6,18`, storage `30 7,19`, docker `0 9,21`. The
  documented maintenance window is **12am–6am LA (07:00–13:00 UTC)**. Infra — the
  source of the package-update findings — never fires in-window, and a `blocked`
  issue does not re-dispatch on its own (ADR-0015 per-state contract makes a
  still-failing blocked finding evidence-only). So medium-risk findings pile up
  with no Podium-native exit. — Evidence: `patrol_config.py:413-421`.
- **Podium already has the scheduling machinery (dormant).** `scheduled_for
  TIMESTAMP NULL` column (`web/api/schema.py:49`); `tracker_podium._scheduled_due()`
  gate (`tracker_podium.py:123,643-651`); `scheduled` label derived from
  `scheduled_for` (`tracker_podium.py:123-128`); `Symphony-Schedule: not_before=…`
  comment grammar (`schedule.py`); `IssueCreate`/`IssuePatch` already accept
  `scheduled_for` (`web/api/main.py:506,534`). **The working scheduler already
  REQUIRES a valid `Symphony-Schedule` comment** for any scheduled issue
  (`scheduler/__init__.py:1174` `"Scheduled ticket is missing a valid
  Symphony-Schedule comment."`) — the column/label is the *flag*, the comment is
  the authoritative *time*. — Evidence: cited code.

## Decisions (→ ADR-0018, `proposed`)

- **Q1 (approval path):** Wire maintenance-window gating (not manual-per-issue, not
  suppress findings).
- **Q2 (mechanism):** Reuse the `Symphony-Schedule` grammar **and** add a
  first-class Schedule control in the Podium UI (new-issue modal + flyout),
  **infra-bindings only**, so the operator can also schedule tasks on the same
  rails the agents use.
- **Q3 (automation level):** **Agent auto-schedules, hands-off.** Instead of
  `SYMPHONY_RESULT: blocked`, medium-risk scheduled updates emit a schedule for the
  next window and apply unattended in-window. Operator accepted the increased
  unattended blast radius on live infra (reboots, package updates with no human in
  the loop), explicitly reversing the agents' current correct-blocking behavior.

## Design shape (see ADR-0018 for full)

- New `SYMPHONY_SCHEDULE: not_before=<iso>` output-contract marker (4th agent
  outcome) → scheduler posts the `Symphony-Schedule:` comment + sets
  `scheduled_for`, issue stays `todo`. **No new issue state** (avoids the C-0211
  CHECK-constraint trap).
- The scheduled dispatch itself is the authorization signal — INFRA_PREAMBLE gains
  a rule: "dispatching from a Symphony schedule ⇒ you are in the approved window,
  apply." Reuses the existing `_with_schedule_context` rendering.
- **Correctness landmine:** dedup must NOT clobber an already-scheduled issue —
  `record_failure` on a `todo`+future-`scheduled_for` issue must be evidence-only,
  or the update slips to "next window" forever.
- Maintenance window = one backend config constant, `00:00–06:00
  America/Los_Angeles`, DST-aware (`zoneinfo`); advisory `not_after` = 06:00 LA.
- Recommended: build marker + in-window apply, verify on one real finding, THEN
  flip INFRA_PREAMBLE (operator chose hands-off as the end state).

## Exclusions

- No secrets read/written. No code changed this session (design only). No infra
  forced; live board observed, not mutated.

## Open Questions / Follow-Ups

- Implementation plan / issues not yet drafted (symphony: marker + scheduler
  handling + UI + window helper + dedup guard; homelab: INFRA_PREAMBLE rule).
- Carried over from the cutover session: stale test
  `test_default_workflow_documents_medium_risk_autonomy`; `ponytail` pi-extension
  ESM packaging bug (host-global tooling debt); homelab runbooks still cite Plane
  CLI/labels (doc debt).
