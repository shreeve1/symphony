---
title: Tracker Contract
type: concept
status: promoted
created: 2026-06-09
updated: 2026-06-17
sources:
  - wiki/raw/tracker_contract.py
  - wiki/raw/adr-0004-tracker-contract.md
  - wiki/raw/bindings.yml
  - tracker_contract.py
  - tracker_adapter.py
  - tracker_podium.py
  - config.py
  - tests/test_tracker_contract.py
  - .kanban/issues/074-tracker-enum-neutral-names.md
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
- `users: tuple[TrackerUserMapping, ...]`

`TrackerUserMapping` carries `homelab_user`, `plane_uuid`, `plane_display_name`, `role` [source: tracker_contract.py#L103-L108].

## Compatibility enums

Issue #074 made the neutral names canonical: `tracker_contract.py` defines `TrackerState`, `TrackerLabel`, and `TrackerUserMapping`; the legacy Plane-prefixed names are compatibility aliases (`PlaneState: TypeAlias = TrackerState`, `PlaneLabel: TypeAlias = TrackerLabel`, `PlaneUserMapping: TypeAlias = TrackerUserMapping`, `PlaneContract: TypeAlias = TrackerContract`) [source: tracker_contract.py#L49-L111, tracker_contract.py#L270-L270, .kanban/issues/074-tracker-enum-neutral-names.md]. `STATE_TO_ROLE`, `LABEL_TO_ROLE`, `ROLE_TO_COMPAT_LABEL`, contract properties, and resolver helpers now annotate against the canonical names [source: tracker_contract.py#L81-L99, tracker_contract.py#L147-L167, tracker_contract.py#L302-L322].

## Resolvers and derived properties

- `state_ids` — `{name: uuid}` for all state Roles whose `uuid` is set [source: wiki/raw/tracker_contract.py#127-129].
- `label_ids` — merge of `extra_label_ids` and label-Role UUIDs (label-Role wins via dict union) [source: wiki/raw/tracker_contract.py#131-137].
- `states`, `labels`, `provisioned_labels` — return the full canonical Enum tuples for compat.
- `overlay_labels` — homelab domain-routing labels (`security`, `infra`, `network`, `media`, `storage`, `docker`) — survived as a class-level constant rather than per-Binding data [source: tracker_contract.py#L159-L167].

## How Bindings populate the contract

`bindings.yml` carries `tracker_contract` per Binding with `state_roles`, `label_roles`, `extra_label_ids`, optional `users`. See [homelab Binding](../entities/binding-homelab.md) and [trading Binding](../entities/binding-trading.md) for filled examples.

## Notes / known seams

- `overlay_labels` returning a fixed homelab-flavoured set is a leak of homelab vocabulary back into the engine-owned module. [ADR-0004](../analyses/adr-0004-tracker-contract.md) says domain labels drop out of the engine entirely; this property is residual compat for tests/non-engine helpers.
- `PlaneState` / `PlaneLabel` / `PlaneUserMapping` / `PlaneContract` now exist only as compatibility aliases; new shared tracker contract annotations should use `TrackerState` / `TrackerLabel` / `TrackerUserMapping`, while engine branching should still prefer `TrackerRole` where possible [source: tracker_adapter.py#L7-L63, tracker_podium.py#L26-L35, config.py#L15-L20].

## Related

- [ADR-0004 — Role-based per-binding Tracker Contract](../analyses/adr-0004-tracker-contract.md)
- [ADR-0002 — Generalize Symphony](../analyses/adr-0002-generalize-symphony.md)
- [Symphony engine](symphony-engine.md) — Tracker abstraction section
- [homelab Binding](../entities/binding-homelab.md), [trading Binding](../entities/binding-trading.md)
