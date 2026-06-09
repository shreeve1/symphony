---
title: homelab Binding
type: entity
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - wiki/raw/bindings.yml
  - bindings.yml
confidence: high
tags: [binding, homelab, plane, project, default-agent, pi]
---

# homelab Binding

Symphony's original Project Binding, now generalized into one of two live entries in `bindings.yml`.

## Identity

| Field | Value |
|---|---|
| name | `homelab` |
| `plane_project_id` | `cff68c17-bff6-452f-89b3-9b570613cfaa` |
| `repo_path` | `/home/james/homelab` |
| `base_branch` | `main` |
| `default_agent` | `pi` |
| `approval.enabled` | `false` |
| `landing.mode` | `local` |

[source: wiki/raw/bindings.yml]

## Tracker Contract

Workspace slug: `homelab`. Project slug: `automations`. Project ID matches `plane_project_id`.

### State Roles (with UUIDs)

| Role | Name | UUID |
|---|---|---|
| `state:todo` | Todo | `ecdab56c-3d58-4da4-bed0-90f0c665deeb` |
| `state:running` | Running | `6d96e0cb-90f5-4581-807c-a7c9a976b422` |
| `state:in-review` | In Review | `ea1ccd3d-82d3-4dd4-8226-192941e8e4c0` |
| `state:blocked` | Blocked | `4b226b00-1e1c-46aa-bbd3-b1e04ad6fc1f` |
| `state:done` | Done | `ef9d22b5-c69c-4707-8ba3-e3db244f2a84` |

### Label Roles (with UUIDs)

| Role | Name | UUID |
|---|---|---|
| `approval-required` | approval-required | `e7480a55-5ab6-417b-a74a-f436ffcf1db7` |
| `mode:plan` | plan | `5a022793-c712-4565-ab70-0183fe04c557` |
| `mode:build` | build | `4ffc7ef9-9159-455c-b3f9-b3a447157aef` |
| `approved` | approved | `67839626-ca7f-4c02-a5e0-12e56a35d909` |
| `scheduled` | scheduled | `9ac7586e-8745-4c22-8a9d-aa83652bee3e` |
| `has-worktree` | has-worktree | (no UUID in bindings.yml) |

### Extra labels (not engine Roles)

Per [ADR-0004](../analyses/adr-0004-tracker-contract.md), these are kept for prompt-routing in `WORKFLOW.md`, not for engine logic: `patrol`, `security`, `infra`, `network`, `media`, `storage`, `docker`.

### Users

| homelab_user | plane_uuid | display_name | role |
|---|---|---|---|
| `james` | `0423d289-e898-43a1-8aaf-b66010dc85ac` | James | admin |

## Notes

- `approval.enabled: false` here is the **engine flag**. The homelab `WORKFLOW.md` still uses the plan/approve flow via labels (`mode:plan` → `approval-required` → `mode:build`). The flag and the flow are distinct.
- This Binding opts into the full Role set (all states + all label Roles); a Binding can omit any optional Role and that behavior just disables (per [ADR-0004](../analyses/adr-0004-tracker-contract.md)).
- The patrol/security/infra/… domain labels were prompt-routing under the homelab-router-owned enum, not engine Roles; they survive in `extra_label_ids` for `WORKFLOW.md` use only.

## Related

- [trading Binding](binding-trading.md)
- [Tracker Contract concept](../concepts/tracker-contract.md)
- [ADR-0004 — Role-based per-binding Tracker Contract](../analyses/adr-0004-tracker-contract.md)
