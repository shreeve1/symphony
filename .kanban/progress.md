# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.


## #028 Podium — models.yml catalog + searchable dropdowns — 2026-06-12

**What changed:** Added repo-root `models.yml`, backend model catalog validator/loader, `/options` model-object response shape, typed frontend `ModelOption`, searchable new-issue comboboxes, agent-filtered model choices, and regression/e2e coverage.
**Files:** `models.yml`, `web/api/main.py`, `web/api/tests/test_issue_create.py`, `web/frontend/lib/api.ts`, `web/frontend/components/NewIssueModal.tsx`, `web/frontend/tests/new-issue.spec.ts`.
**Decisions:** Model catalog is git-tracked YAML authored config; `preferred_model` and `preferred_agent` stay free-text end to end, while Skill remains selection-only because backend FK validation still applies.
**Conventions established:** `/api/bindings/{name}/options` returns `models` as `{id, agent, label?, provider?}` objects loaded through `_validate_models`; missing or invalid `models.yml` degrades to an empty model list without failing the endpoint.
**Notes for next iteration:** #032 should reuse `_validate_models()` for the `symphony-models` skill instead of reimplementing catalog validation.

## #029 Podium — gated interval polling for engine-driven state freshness — 2026-06-12

**What changed:** Added shared frontend polling helpers, active-aware board refetch intervals, run/log detail refetch intervals, and direct-SQLite Playwright coverage proving polling without WebSocket fanout.
**Files:** `web/frontend/lib/polling.ts`, `web/frontend/app/[binding]/page.tsx`, `web/frontend/components/RunDetailPanel.tsx`, `web/frontend/tests/fixtures.ts`, `web/frontend/tests/live-sync.spec.ts`.
**Decisions:** Engine-driven state freshness remains frontend polling per ADR-0006; WebSocket behavior stays unchanged for API-process optimistic updates.
**Conventions established:** Use `issue.state === "running"` or `latest_run_state in {"queued", "running"}` for board activity; use Run `state in {"queued", "running"}` for Run detail/log polling.
**Notes for next iteration:** #030 can rely on Run detail refetch-on-terminal behavior and only needs elapsed timer rendering/hand-off.
