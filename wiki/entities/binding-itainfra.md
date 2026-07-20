---
title: itainfra Binding
type: entity
status: promoted
created: 2026-07-20
updated: 2026-07-20
sources:
  - bindings.yml
  - wiki/raw/sessions/2026-07-20-itainfra-binding-onboard.md
confidence: high
tags: [binding, itainfra, podium, coding, remote, n8n, pi, rpc, smoke-tested]
---

# itainfra Binding

`itainfra` is a Podium-backed remote **coding** binding for `/home/itadmin/itainfra`, onboarded 2026-07-20 with Pi RPC dispatch over SSH to the existing n8n host group [source: bindings.yml] [source: wiki/raw/sessions/2026-07-20-itainfra-binding-onboard.md#durable-facts].

## Configuration

| Field | Value |
|---|---|
| `name` | `itainfra` |
| `type` | `coding` |
| `tracker` | `podium` |
| `repo_path` | `/home/itadmin/itainfra` |
| `base_branch` | `main` |
| `default_agent` | `pi` |
| `pi_mode` | `rpc` |
| `approval.enabled` | `false` |
| `landing.mode` | `local` |
| `remote.host` | `100.95.224.218` |
| `remote.user` | `itadmin` |
| `remote.host_alias` | `n8n` |
| `plane_project_id` | `itainfra` (transitional config compatibility; not a Plane call) |

The shared `n8n` alias groups this repository with the existing bindings on the same SSH host without changing dispatch addressing [source: bindings.yml] [source: wiki/raw/sessions/2026-07-20-itainfra-binding-onboard.md#decisions].

## Onboarding evidence

Symphony commit `fe6ffd2` added the binding. The scheduler restarted on code SHA `9675c6e` with ten bindings, passed the global RPC probe, reconciled `itainfra`, and entered the dispatch loop without matched errors [source: wiki/raw/sessions/2026-07-20-itainfra-binding-onboard.md#durable-facts].

Smoke Issue `554` produced one implement Run, `3237`, through `pi` / `pi-duo` / `Duo:high`. The Run exited `0` with verdict `done`; because the operator smoke kept `auto_land=false`, the Issue parked in `in_review` and did not launch an auto-land review [source: wiki/raw/sessions/2026-07-20-itainfra-binding-onboard.md#durable-facts].

## Policy note

Remote Pi RPC bindings require `type: coding`, so no infra `WORKFLOW.md` was authored. The target repository has a top-level `CLAUDE.md`, which supplies repository conventions and safety policy [source: wiki/raw/sessions/2026-07-20-itainfra-binding-onboard.md#decisions].

## Related

- [n8n remote dispatch architecture](/analyses/adr-0012-remote-binding-ssh-exec.md)
- [Symphony skill suite](/analyses/symphony-skills-index.md)
- [pi-rmm binding](/entities/binding-pi-rmm.md)

# Citations

- `bindings.yml`
- `wiki/raw/sessions/2026-07-20-itainfra-binding-onboard.md`
