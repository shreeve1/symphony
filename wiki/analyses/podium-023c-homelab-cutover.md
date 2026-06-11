---
title: "#023c Podium homelab cutover + infra role projection"
type: analysis
status: promoted
created: 2026-06-11
updated: 2026-06-11
sources:
  - bindings.yml
  - tracker_podium.py
  - web/api/schema.py
  - web/api/migrations/versions/0003_infra_role_columns.py
  - web/api/main.py
  - web/frontend/components/IssueFlyout.tsx
  - web/README.md
  - CONTEXT.md
  - tests/test_tracker_podium_infra.py
  - tests/test_main.py
  - .kanban/issues/023c-podium-homelab-cutover.md
  - .kanban/progress.md
confidence: high
tags: [podium, homelab, cutover, tracker-adapter, infra-roles, live-smoke, plane-retirement]
---

# #023c Podium homelab cutover + infra role projection

## Outcome

The `homelab` binding now declares `tracker: podium`, so both active Symphony bindings (`homelab` and `trading`) use Podium. The old homelab Plane `tracker_contract` remains in `bindings.yml` as a commented rollback block until #023d archives Plane [source: bindings.yml; .kanban/issues/023c-podium-homelab-cutover.md].

## Infra role projection

Podium gained issue columns for infra-binding roles: `approval_required BOOLEAN DEFAULT FALSE`, `approved BOOLEAN DEFAULT FALSE`, and `scheduled_for TIMESTAMP NULL`. Runtime `SCHEMA_SQL` and Alembic revision `0003_infra_role_columns` remain schema-parity tested by `tests/test_alembic_baseline.py` [source: web/api/schema.py; web/api/migrations/versions/0003_infra_role_columns.py; tests/test_alembic_baseline.py].

`PodiumTrackerAdapter` now projects `TrackerRole.APPROVAL_REQUIRED` and `TrackerRole.APPROVED` to booleans, and `TrackerRole.SCHEDULED` to a due `scheduled_for` timestamp. The new `tests/test_tracker_podium_infra.py` covers add/remove projection for all three roles [source: tracker_podium.py; tests/test_tracker_podium_infra.py].

## UI/API surface

Podium issue API rows now include `binding_type`, `approval_required`, `approved`, and `scheduled_for`. The frontend renders approval/schedule chips only when `issue.binding_type === "infra"`, so homelab sees them and coding bindings such as trading hide them [source: web/api/main.py; web/frontend/lib/api.ts; web/frontend/components/IssueFlyout.tsx].

## Live cutover verification

The live repo-root Podium DB was migrated to head, `symphony-host.service` restarted successfully, and startup reconcile completed for both bindings. A live homelab smoke issue (`18`) dispatched through Podium, ran with cwd `/home/james/homelab`, produced Run `11`, and populated verdict/log/comments/context fields. In unattended mode, the smoke issue was inserted directly into Podium SQLite because browser UI auth credentials were unavailable to the worker [source: .kanban/issues/023c-podium-homelab-cutover.md#implementation-notes; .kanban/progress.md].

During cutover, stale homelab e2e Todo issues `9`–`16` were parked as Blocked to prevent unintended live dispatch. Older e2e issues `5`–`8` had already dispatched successfully before they could be parked [source: .kanban/issues/023c-podium-homelab-cutover.md#implementation-notes; .kanban/progress.md].

## Documentation and rollback

`CONTEXT.md` now treats Mode as historical, rewrites Run Worktree and Landing around Podium's opt-in worktree model, and notes that Plane is retired for active bindings. `web/README.md` documents rollback: remove `tracker: podium`, uncomment the Plane rollback block if present, and restart `symphony-host.service` [source: CONTEXT.md; web/README.md].

## Verification

Implementation verification passed: `uv run pytest` (586 passed, 1 skipped), `pnpm exec tsc --noEmit`, live `alembic upgrade head`, service restart, live smoke, touched-file LSP diagnostics with no critical errors, and fresh Ralph review `RALPH_REVIEW: PASS` [source: .kanban/issues/023c-podium-homelab-cutover.md; .kanban/progress.md].

## Claims

C-0104 through C-0106 in [CLAIMS.md](../CLAIMS.md).
