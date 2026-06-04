---
id: 001
title: Role-based Tracker Contract — sever the homelab_router import
status: in-progress
blocked_by: []
updated: 2026-06-04
actor: ralph
parent: null
priority: 0
created: 2026-06-04
---

## What to build

Replace the engine's hard import of label/state vocabulary from the bound repo
(`from homelab_router.plane_contract import PlaneLabel, PlaneState`, `scheduler.py:30`)
with a Symphony-owned, role-based contract. The engine branches only on **Roles**
— `mode:plan`, `mode:build` (execute = absence of both), the `agent:*` dispatch
override, `approval-required`, `approved`, `scheduled`, and the five states
(Todo / In Review / Running / Blocked / Done). A per-binding contract maps each
supported Role to that project's concrete label/state **name + UUID**. Roles a
binding omits simply disable the corresponding behavior (e.g. no `scheduled`
label ⇒ no scheduled-release path, not an error).

homelab becomes one contract instance whose vocabulary happens to also define
`scheduled`, `approved`, and its domain labels (domain labels are no longer engine
concerns — they move to per-repo WORKFLOW.md later). Drop the
`/home/james/homelab/automation/homelab-stack/src` entry from `pyproject.toml`
`[tool.pytest.ini_options] pythonpath` once the import is gone.

See `docs/adr/0004-role-based-per-binding-tracker-contract.md`.

## Acceptance criteria

- [ ] No module under the symphony package imports from `homelab_router`.
- [ ] A `pyproject.toml` pythonpath no longer references the homelab src tree.
- [ ] `_resolve_mode`, the scheduled-release path, and the approval flow resolve via contract Roles, not enum values.
- [ ] A contract that omits an optional Role (`scheduled`/`approved`/`approval-required`) disables that behavior without raising.
- [ ] Required Roles (mode labels + the five states) missing from a contract is a clear config error.
- [ ] Existing dispatch/verdict behavior for the homelab contract is unchanged (regression-covered by the suite).

## Verification

`uv run pytest`

## Blocked by

None — can start immediately.
