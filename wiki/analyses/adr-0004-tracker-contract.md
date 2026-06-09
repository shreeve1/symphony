---
title: ADR-0004 — Role-based per-binding Tracker Contract
type: decision
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - wiki/raw/adr-0004-tracker-contract.md
  - docs/adr/0004-role-based-per-binding-tracker-contract.md
confidence: high
tags: [adr, tracker-contract, role, multi-project, label, state, plane-contract]
---

# ADR-0004 — Reference tracker vocabulary by role, in a per-binding contract

## Problem

Symphony's engine currently imports its label and state vocabulary as a frozen enum from the very repo it operates on: `from homelab_router.plane_contract import PlaneLabel, PlaneState` (`scheduler.py:30`). `_resolve_mode`, the scheduled-release path, and the plan-approval flow all branch directly on those enum *values* (e.g. `PlaneLabel.BUILD.value`, `SCHEDULED`, `APPROVED`). This is the keystone blocker for going multi-project [source: wiki/raw/adr-0004-tracker-contract.md#3]:

- the engine hard-depends on a Python package living inside one target repo
- every Binding would drag in homelab's full label set
- per-project UUID maps are unique per Plane project so a single global contract cannot serve N projects
- new labels like `agent:claude` / `agent:pi` aren't representable without editing the enum
- scaffolded projects that omit `scheduled` / `approved` would hit code paths whose label UUIDs don't resolve

## Decision

Make the engine branch on a small set of **Roles** rather than on concrete label/state strings, and carry the concrete vocabulary in a **per-Binding contract**. Roles are the things the engine logic actually keys off [source: wiki/raw/adr-0004-tracker-contract.md#5]:

- `mode:plan` and `mode:build` (execute is the absence of both)
- `agent:*` dispatch override
- `approval-required` gate
- `approved` plan-approval signal
- `scheduled` release window
- the five workflow states: Todo / In Review / Running / Blocked / Done

Each Binding's contract maps every Role it supports to that project's actual label/state *name plus UUID*. Roles a Binding omits simply disable the corresponding behaviour — a code repo with no `scheduled` label has no scheduled-release path rather than an erroring one.

The vocabulary moves out of `homelab_router` into a package Symphony owns. Homelab becomes just another Binding whose contract happens to also define `scheduled`, `approved`, and (now irrelevant to the engine) its domain labels.

The homelab domain labels (patrol/security/infra/…) are not engine Roles at all — they were prompt-routing, which moves to the per-repo `WORKFLOW.md`, so they drop out of the engine entirely [source: wiki/raw/adr-0004-tracker-contract.md#5].

## Alternatives rejected

- **Move enum verbatim into Symphony but keep it global**: still forces every project onto one label set, keeps `agent:*` an enum edit, makes per-repo variation awkward.
- **Fully free-form per-Binding label maps with no engine-owned vocabulary**: would dissolve the fixed contract that mode, approval, and scheduling logic rely on, trading guarantees for flexibility the design doesn't need.

Role indirection is the middle path — a fixed, engine-owned set of *Roles* (strong guarantees) bound to per-project *names and UUIDs* (per-repo flexibility) [source: wiki/raw/adr-0004-tracker-contract.md#7].

## Composition with ADR-0002

This is the concrete shape of the Tracker Adapter seam from [ADR-0002](adr-0002-generalize-symphony.md): the adapter resolves an issue's Roles for its Binding instead of the engine reading global enum values [source: wiki/raw/adr-0004-tracker-contract.md#9].

## Accepted cost

Engine-wide refactor of every site that currently compares against `PlaneLabel` / `PlaneState` values, plus defining which Roles are required (mode labels, states) versus optional (approval/approved/scheduled), and making optional-Role absence degrade gracefully rather than error.

## Related

- [ADR-0002](adr-0002-generalize-symphony.md) — adapter seams
- [Tracker Contract concept](../concepts/tracker-contract.md) — implementation
- [Symphony engine](../concepts/symphony-engine.md) — Tracker abstraction section
