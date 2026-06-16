---
title: trading Binding
type: entity
status: promoted
created: 2026-06-09
updated: 2026-06-15
sources:
  - wiki/raw/bindings.yml
  - bindings.yml
  - wiki/raw/sessions/2026-06-11-podium-023d-trading-plane-archive.md
  - wiki/raw/sessions/2026-06-15-trading-binding-offboard.md
confidence: high
tags: [binding, trading, plane, project, default-agent, pi, multi-project, podium, archived, offboarded, removed]
---

# trading Binding

Second Project Binding, added after Symphony was generalized for multi-project use. Demonstrates a leaner Role set than homelab — no `scheduled`, no `approved`, no `has-worktree` UUID, no domain labels beyond `agent:*`.

> **OFFBOARDED (2026-06-15, purge):** trading was removed via
> `/symphony-offboard-project trading` in **purge** mode — its `bindings.yml`
> entry was dropped and its Podium `binding`/`issue`/`run`/`binding_settings`
> rows were **deleted** (`db_action='deleted'`, 1 issue + 1 run; irreversible
> except from a `podium.db` backup). After restart the live binding set is
> **2: homelab, symphony** — trading is no longer dispatched. Everything below
> is **historical**. See
> [offboard session](../raw/sessions/2026-06-15-trading-binding-offboard.md)
> and C-0212. Live bindings: [homelab](binding-homelab.md),
> [symphony](binding-symphony.md).

> **Status (2026-06-11, #023d):** trading is on Podium (`tracker: podium`) and its
> Plane project (`201a3995-...`) was **archived**. The `tracker_contract` block
> below was **removed from `bindings.yml`**; trading now resolves to
> `DEFAULT_CONTRACT` (`config.py:391`). The Tracker Contract / Role tables below
> are retained as **historical** (the pre-archive `wiki/raw/bindings.yml`
> snapshot) — see [#023d archive](../analyses/podium-023d-trading-plane-archive.md)
> and C-0107. The binding still carries the required `plane_project_id`.

## Identity

| Field | Value |
|---|---|
| name | `trading` |
| `plane_project_id` | `201a3995-c738-4f5a-acbe-7608f302301e` |
| `repo_path` | `/home/james/trading/crypto-trading-agents` |
| `base_branch` | `main` |
| `default_agent` | `pi` |
| `approval.enabled` | `false` |
| `landing.mode` | `local` |

[source: wiki/raw/bindings.yml]

## Tracker Contract (historical — removed 2026-06-11)

The block below documents the trading `tracker_contract` as it stood before
#023d removed it. It no longer exists in `bindings.yml`; trading resolves to
`DEFAULT_CONTRACT`. Retained for the rollback/audit record only.

No `workspace_slug` in this entry (homelab has one; trading doesn't — defaults presumably resolve through code). Project slug: `trading`. Project ID matches `plane_project_id`.

### State Roles (with UUIDs)

| Role | Name | UUID |
|---|---|---|
| `state:todo` | Todo | `9f67c662-45c0-4d04-b1c2-7b1e1996d868` |
| `state:in-review` | In Review | `6e939873-c8e2-441d-a2c6-cc2e5624c89c` |
| `state:running` | Running | `63cdba03-fd48-4331-b093-a9ea756d0512` |
| `state:blocked` | Blocked | `fdc408d4-bf6a-4a97-b934-fcc8c819dbfb` |
| `state:done` | Done | `d3419e46-b00e-4eec-ac5b-f6b927e2c7a6` |

### Label Roles (with UUIDs)

| Role | Name | UUID |
|---|---|---|
| `mode:plan` | plan | `8041d267-1e1e-4b8e-988e-b035f1a6ea37` |
| `mode:build` | build | `1e8b7d18-94dd-48c9-b273-bf781f2de01b` |
| `approval-required` | approval-required | `0d492a5f-4d6f-4937-90ca-909cf7f185b7` |
| `has-worktree` | has-worktree | (no UUID in bindings.yml) |

### Extra labels (not engine Roles)

`agent:claude` (`2a969e9f-69e2-47a3-a6d0-1c9349fd62c1`), `agent:pi` (`784b2719-39ed-4ce9-9f8e-f07224b33df1`).

## Roles intentionally omitted

`approved` and `scheduled` Roles are absent. Per [ADR-0004](../analyses/adr-0004-tracker-contract.md), Roles a Binding omits simply disable the corresponding behaviour. For `trading`:

- no plan-approval gate via Plane label flow
- no scheduled-release path (and no 12am-6am maintenance window applies)

If trading later needs either, add the Role + UUID via `symphony-project-scaffold` (or by hand) and the engine path activates without a code change.

## Notes

- No `users:` block here; homelab has James pinned with admin role.
- No `extra_label_ids` for domain labels — trading does not (yet) carry prompt-routing labels.

## Related

- [homelab Binding](binding-homelab.md)
- [Tracker Contract concept](../concepts/tracker-contract.md)
- [symphony-project-scaffold skill](../../CLAUDE.md) — created this Binding via `chore: add trading binding via scaffold` (commit `f4f696f`)
