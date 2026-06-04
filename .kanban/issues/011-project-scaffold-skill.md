---
id: 011
title: Project Scaffold skill (mock-tested; live run gated)
status: pending
blocked_by: [7, 8]
parent: null
priority: 0
created: 2026-06-04
---

## What to build

A skill that stands up a new Plane project to match a repo and registers it with
Symphony in one pass: create the project in the `homelab` workspace from a
standard template (states Todo / In Review / Running / Blocked / Done; labels
plan / build / approval-required + agent:claude / agent:pi), introspect the fresh
per-project state/label UUIDs onto the binding, append a complete entry to
`bindings.yml` (#007), and drop a `WORKFLOW.md` stub (#008) for the human to
author. It does NOT carry the homelab-era domain labels.

**Live-mutation gate:** real project creation is a live Plane mutation and is
forbidden without James's explicit approval. Therefore build and verify this
slice **against a mocked tracker** — assert the create-project request shape, the
UUID introspection mapping, the `bindings.yml` append, and the `WORKFLOW.md` stub
drop, all without touching live Plane. The actual live run stays a manual,
approval-gated step outside the Ralph loop.

See the **Project Scaffold** glossary entry in `CONTEXT.md`.

## Acceptance criteria

- [ ] Against a mocked tracker, the skill issues a create-project request matching the standard-template shape (states + labels, no domain labels).
- [ ] Fresh per-project state/label UUIDs are introspected and mapped onto a new binding contract.
- [ ] A complete, valid entry is appended to `bindings.yml` and re-loads cleanly via #007.
- [ ] A `WORKFLOW.md` stub is written to the target repo root.
- [ ] No test performs a live Plane mutation; the live path is explicitly gated behind manual approval.
- [ ] Suite green.

## Verification

`uv run pytest`

## Blocked by

- Blocked by #7
- Blocked by #8
