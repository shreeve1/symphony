---
id: 067
title: Stop shipping Plane secret/env to podium-binding agents
status: pending
blocked_by: []
parent: null
priority: 0
created: 2026-06-17
---

## What to build

Finding L6-02(a) (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`), the near-term security half. All four live bindings are `tracker: podium`, yet every agent subprocess is injected with the Plane callback env — including the `SYMPHONY_PLANE_API_KEY` secret (`agent_runner.py:213-218`, `_remote_exports:383-393`) — plus the shipped `plane` helper (`run_agent:285`, `run_remote_agent:454`, `run_pi_rpc_agent:600`), for a tracker it never calls. Removes a present secret-exposure surface.

- Stop injecting `SYMPHONY_PLANE_API_KEY` / `SYMPHONY_PLANE_*` / `PLANE_DASHBOARD_URL` callback env into agent env on **podium-tracker** bindings.
- Gate shipping the `plane` helper to **plane-tracker** bindings only (or document the no-op if left shipped).
- Preserve full Plane env + helper for plane-tracker bindings (back-compat).
- Before gating, confirm no live podium binding's agent actually invokes `plane` (state is driven purely through SYMPHONY_RESULT markers on podium).

## Acceptance criteria

- [ ] On a podium binding, the constructed agent env does **not** contain `SYMPHONY_PLANE_API_KEY` — covered by a test asserting its absence.
- [ ] On a plane binding (constructed in test), the Plane callback env is still injected — back-compat test.
- [ ] The `plane` helper is shipped only for plane-tracker bindings, or its podium no-op is documented in code.
- [ ] `uv run pytest` passes, including the new podium-no-secret test.

## Verification

`uv run pytest`

## Blocked by

None — can start immediately.
