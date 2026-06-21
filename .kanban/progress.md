# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

## #93 Schedule foundations — 2026-06-21

**What changed:** Added shared maintenance-window computation, `next_window` schedule parsing, and Podium single-blob latest control-line selection.
**Files:** `schedule.py`, `scheduler/__init__.py`, `tests/test_schedule.py`, `tests/test_scheduler.py`, `.kanban/issues/093-schedule-foundations-next-window-prefer-last.md`
**Decisions:** Window constants now live in `schedule.py`; scheduler keeps compatibility aliases but delegates to `schedule.next_maintenance_window`. `prefer_last` remains opt-in and is enabled only for Podium-style single-blob comments.
**Verification:** `uv run pytest tests/test_schedule.py tests/test_scheduler.py -q` (226 passed); LSP diagnostics clean for touched Python files.

## #94 SYMPHONY_SCHEDULE output marker — 2026-06-21

**What changed:** Added stdout parsing for `SYMPHONY_SCHEDULE` markers, stripped schedule marker lines from summary/question blocks, and documented schedule as the fourth terminal outcome.
**Files:** `scheduler/markers.py`, `scheduler/__init__.py`, `prompt_renderer.py`, `tests/test_schedule.py`, `tests/test_prompt_renderer.py`, `.kanban/issues/094-symphony-schedule-marker.md`
**Decisions:** The marker parser reuses `schedule.parse_schedule_comment` so explicit timestamps, `next_window`, and non-empty reasons follow the same grammar as tracker schedule comments. Scheduling policy remains out of `INFRA_PREAMBLE`; the output contract only documents the mechanism.
**Conventions established:** Schedule terminal outcomes use a column-0 `SYMPHONY_SCHEDULE: not_before=<next_window|iso8601-with-offset> reason="..."` line plus a summary block.
**Notes for next iteration:** Issue #95 wires this parser into terminal classification and must decide malformed-marker blocking behavior from a present-but-unparseable marker.
**Verification:** `uv run pytest tests/test_schedule.py tests/test_prompt_renderer.py tests/test_prompt_renderer_podium.py -q` (90 passed); fresh review passed; LSP diagnostics clean for touched Python files.

## #95 Scheduler terminal schedule handler — 2026-06-21

**What changed:** Wired `SYMPHONY_SCHEDULE` stdout markers into `_classify_terminal` so infra agents can defer issues into the maintenance window by posting the canonical schedule comment, adding the scheduled label, and returning the issue to TODO.
**Files:** `scheduler/__init__.py`, `tests/test_scheduler.py`, `.kanban/issues/095-scheduler-terminal-schedule-handler.md`
**Decisions:** Schedule marker handling is infra-only; malformed/past/reasonless markers block explicitly, while coding bindings ignore markers and continue normal terminal classification. Valid schedule markers finish Runs as `succeeded` with `verdict=None` to avoid introducing a new issue state.
**Conventions established:** Schedule terminal handling order is comment → scheduled label → TODO; marker scheduling returns `agent-marker-scheduled` and logs `state_scheduled`.
**Notes for next iteration:** Issue #98 can now rely on marker-scheduled issues being held by the existing scheduled gate and released by the existing due-schedule selector.
**Verification:** `uv run pytest tests/test_scheduler.py -q` (172 passed); actionable review fixed approval-gate precedence, malformed-marker coding ignore, mutation-order/run-record coverage, and added `action_reviewed`; LSP diagnostics clean for touched Python files.

## #96 Manual schedule API — 2026-06-21

**What changed:** Added infra-only manual schedule/unschedule endpoints, exposed `binding_type` on `/api/bindings`, and added atomic create-and-schedule support.
**Files:** `web/api/main.py`, `web/api/tests/test_schedule_endpoint.py`, `web/api/tests/test_endpoints.py`, `.kanban/issues/096-manual-schedule-api-endpoint.md`
**Decisions:** Manual scheduling stores `scheduled_for=now` as the hold flag while the canonical `Symphony-Schedule:` comment carries the actual not-before time; explicit past timestamps are rejected, but `next_window` is accepted even when it resolves to the current window start.
**Conventions established:** Schedule API is infra-only and uses the same label/comment rails as agent-emitted schedule markers; `IssueCreate.schedule` is the only race-free create-time scheduling path.
**Notes for next iteration:** Issue #97 can rely on `/api/bindings` `binding_type`, `POST`/`DELETE /schedule`, and `IssueCreate.schedule` for the frontend control.
**Verification:** `uv run pytest web/api/tests/test_schedule_endpoint.py web/api/tests/test_endpoints.py -q` (9 passed); fresh review passed; LSP diagnostics clean for touched Python files.

## #97 Frontend schedule controls — 2026-06-21

**What changed:** Added the infra-only Podium Schedule control in the new-issue modal and issue flyout, wired create-time `schedule` payloads plus existing-issue `POST`/`DELETE /schedule`, and added a board-card Scheduled chip.
**Files:** `web/frontend/components/ScheduleControl.tsx`, `web/frontend/components/NewIssueModal.tsx`, `web/frontend/components/IssueFlyout.tsx`, `web/frontend/components/IssueCard.tsx`, `web/frontend/lib/api.ts`, `web/frontend/tests/schedule.spec.ts`, `web/frontend/pnpm-workspace.yaml`, `.kanban/issues/097-frontend-schedule-control-infra-only.md`
**Decisions:** The modal derives infra/coding from `/api/bindings.binding_type`; custom datetime input is converted to ISO8601 with the browser's local offset before submission; `scheduled_for` remains a hold indicator while the flyout parses the latest `Symphony-Schedule` line for display.
**Conventions established:** Frontend manual scheduling uses the schedule endpoints only; `IssuePatch.scheduled_for` is not used as the UI scheduling path.
**Notes for next iteration:** Issue #98 is still the manual/cross-repo homelab policy/dedup slice; this Ralph run did not touch it.
**Verification:** `cd web/frontend && pnpm test:e2e schedule.spec.ts && pnpm build` (3 Playwright tests passed; Next build passed); fresh review passed with a note that `web/frontend/pnpm-workspace.yaml` is a build prerequisite for approved `sharp` builds; LSP diagnostics had only pre-existing non-critical client-component/FormEvent warnings.
