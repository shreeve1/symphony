---
title: Tracker Contract
type: concept
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - wiki/raw/tracker_contract.py
  - wiki/raw/adr-0004-tracker-contract.md
  - wiki/raw/bindings.yml
  - tracker_contract.py
confidence: high
tags: [tracker-contract, role, plane-contract, multi-project, adapter]
---

# Tracker Contract

The per-Binding mapping from engine-facing **Roles** to a Plane project's concrete label/state names plus UUIDs. The concrete shape of the Tracker Adapter seam declared in [ADR-0002](../analyses/adr-0002-generalize-symphony.md) and motivated in [ADR-0004](../analyses/adr-0004-tracker-contract.md).

## Engine Roles

Roles are the things the scheduler branches on. The full set, from `tracker_contract.py:14-25` [source: wiki/raw/tracker_contract.py]:

```
TrackerRole
├── label roles
│   ├── MODE_PLAN          "mode:plan"
│   ├── MODE_BUILD         "mode:build"
│   ├── APPROVAL_REQUIRED  "approval-required"
│   ├── APPROVED           "approved"
│   ├── SCHEDULED          "scheduled"
│   └── HAS_WORKTREE       "has-worktree"
└── state roles
    ├── STATE_TODO         "state:todo"
    ├── STATE_IN_REVIEW    "state:in-review"
    ├── STATE_RUNNING      "state:running"
    ├── STATE_BLOCKED      "state:blocked"
    └── STATE_DONE         "state:done"
```

`execute` mode is the absence of both `MODE_PLAN` and `MODE_BUILD`, per CONTEXT.md and [ADR-0004](../analyses/adr-0004-tracker-contract.md).

## Required vs optional Roles

Required (engine raises `ValueError` if missing) [source: wiki/raw/tracker_contract.py#28-38]:

- `REQUIRED_LABEL_ROLES` = `MODE_PLAN`, `MODE_BUILD`
- `REQUIRED_STATE_ROLES` = all five states

Optional (absence disables behaviour) [source: wiki/raw/tracker_contract.py#174]:

- `APPROVAL_REQUIRED`, `APPROVED`, `SCHEDULED`, `HAS_WORKTREE`

`label_binding(role)` raises; `optional_label_binding(role)` returns `None`.

## Data shape

`RoleBinding` is a frozen dataclass `(name: str, uuid: str = "")` [source: wiki/raw/tracker_contract.py#41-46]. `TrackerContract` carries [source: wiki/raw/tracker_contract.py#107-125]:

- `version: str = "1.0"`
- `workspace_slug: str` (default `"homelab"`)
- `project_slug: str` (default `"automations"`)
- `project_id: str`
- `state_roles: dict[TrackerRole, RoleBinding]`
- `label_roles: dict[TrackerRole, RoleBinding]`
- `extra_label_ids: dict[str, str]` — non-engine labels (domain labels for homelab, agent:* for trading)
- `users: tuple[PlaneUserMapping, ...]`

`PlaneUserMapping` carries `homelab_user`, `plane_uuid`, `plane_display_name`, `role` [source: wiki/raw/tracker_contract.py#99-105].

## Compatibility enums

The module still exports `PlaneState` and `PlaneLabel` Enum classes plus `STATE_TO_ROLE`, `LABEL_TO_ROLE`, `ROLE_TO_COMPAT_LABEL` maps [source: wiki/raw/tracker_contract.py#49-96]. Per the class docstring these are "Compatibility names for labels used by tests and non-engine helpers" — the engine itself branches on `TrackerRole`, but the enums survive for callers that pre-date the refactor.

## Resolvers and derived properties

- `state_ids` — `{name: uuid}` for all state Roles whose `uuid` is set [source: wiki/raw/tracker_contract.py#127-129].
- `label_ids` — merge of `extra_label_ids` and label-Role UUIDs (label-Role wins via dict union) [source: wiki/raw/tracker_contract.py#131-137].
- `states`, `labels`, `provisioned_labels` — return the full Enum tuples for compat.
- `overlay_labels` — homelab domain-routing labels (`security`, `infra`, `network`, `media`, `storage`, `docker`) — survived as a class-level constant rather than per-Binding data [source: wiki/raw/tracker_contract.py#152-160].

## How Bindings populate the contract

`bindings.yml` carries `tracker_contract` per Binding with `state_roles`, `label_roles`, `extra_label_ids`, optional `users`. See [homelab Binding](../entities/binding-homelab.md) and [trading Binding](../entities/binding-trading.md) for filled examples.

## Notes / known seams

- `overlay_labels` returning a fixed homelab-flavoured set is a leak of homelab vocabulary back into the engine-owned module. [ADR-0004](../analyses/adr-0004-tracker-contract.md) says domain labels drop out of the engine entirely; this property is residual compat for tests/non-engine helpers.
- `PlaneState` / `PlaneLabel` enum classes pre-date the Role refactor; their continued export is "non-engine helpers" only. New engine code should reference `TrackerRole` directly.

## Related

- [ADR-0004 — Role-based per-binding Tracker Contract](../analyses/adr-0004-tracker-contract.md)
- [ADR-0002 — Generalize Symphony](../analyses/adr-0002-generalize-symphony.md)
- [Symphony engine](symphony-engine.md) — Tracker abstraction section
- [homelab Binding](../entities/binding-homelab.md), [trading Binding](../entities/binding-trading.md)
