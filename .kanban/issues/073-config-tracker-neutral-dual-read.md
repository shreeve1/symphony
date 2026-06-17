---
id: 073
title: Config tracker-neutral env dual-read (code side)
status: pending
blocked_by: [63]
parent: null
priority: 0
created: 2026-06-17
---

## What to build

Phase 6 / finding L5-02 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`), **code side only**. The config/env vocabulary names Plane though it serves both trackers (`config.py:25-38` `_REQUIRED_ENV`/`_BINDINGS_ENV` `PLANE_*`; `SymphonyConfig` fields `plane_api_url`/`plane_api_key`/`plane_project_id`/`plane_frontend_url`/`plane_dashboard_url`; `ProjectBinding.plane_project_id`).

Introduce tracker-neutral `SYMPHONY_TRACKER_*` env names and tracker-neutral field/property accessors, **read alongside** the legacy `PLANE_*` names (dual-read). Legacy `PLANE_*` must keep working unchanged so the current live `symphony-host.service` unit needs no edit.

**Out of scope (operator follow-up, not this issue):** renaming the live `symphony-host.service` unit + `symphony-host.env` to the new names. Dual-read keeps the existing `PLANE_*` unit working; the on-disk rename is a separate coordinated James step after this code ships and is **not** part of this issue's acceptance. Do not edit the unit or env file here.

## Acceptance criteria

- [ ] Config reads the new `SYMPHONY_TRACKER_*` env names **and** the legacy `PLANE_*` names (dual-read); precedence is documented in code.
- [ ] A test loads config from legacy `PLANE_*` env only and succeeds unchanged (back-compat).
- [ ] A test loads config from the new `SYMPHONY_TRACKER_*` env only and succeeds.
- [ ] No change to `/home/james/symphony-host.env` or `symphony-host.service` in this issue.
- [ ] `uv run pytest` passes.

## Verification

`uv run pytest`

## Blocked by

- Blocked by #063 (serializes `config.py` edits after the `KNOWN_AGENTS` change).
