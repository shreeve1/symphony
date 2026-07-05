---
title: pi-rmm Binding
type: entity
status: promoted
created: 2026-07-05
updated: 2026-07-05
sources:
  - bindings.yml
  - wiki/raw/sessions/2026-07-05-pi-rmm-binding-onboard.md
confidence: high
tags: [binding, pi-rmm, podium, coding, default-agent, pi, smoke-tested]
---

# pi-rmm Binding

`pi-rmm` is a Podium-backed **coding** binding for `/home/james/pi-rmm`, onboarded 2026-07-05 with the default local Pi RPC posture [source: bindings.yml] [source: wiki/raw/sessions/2026-07-05-pi-rmm-binding-onboard.md#durable-facts].

## Configuration

| Field | Value |
|---|---|
| `name` | `pi-rmm` |
| `type` | `coding` |
| `tracker` | `podium` |
| `repo_path` | `/home/james/pi-rmm` |
| `base_branch` | `main` |
| `default_agent` | `pi` |
| `pi_mode` | `rpc` |
| `approval.enabled` | `false` |
| `landing.mode` | `local` |
| `plane_project_id` | `pi-rmm` (transitional config-compat only; not a Plane call) |

Podium side has a live `binding` row and `binding_settings` row for `pi-rmm` in `/home/james/symphony/podium.db` [source: wiki/raw/sessions/2026-07-05-pi-rmm-binding-onboard.md#durable-facts].

## Onboarding evidence

The target path was first initialized as a git repo on `main` and committed as `c7d955e Initial commit`; without that, coding dispatch/worktree operations would fail [source: wiki/raw/sessions/2026-07-05-pi-rmm-binding-onboard.md#durable-facts].

Symphony commit `8bdcbc5 Add pi-rmm binding` appended the `bindings.yml` entry, and `symphony-host.service` restarted onto `code_sha=8bdcbc5` with `bindings=7`. Startup logs showed `pi_rpc_probe_ok` and `reconcile_startup_done binding=pi-rmm cleaned=0` [source: wiki/raw/sessions/2026-07-05-pi-rmm-binding-onboard.md#durable-facts].

Smoke Issue `225` produced Run `851`, which succeeded with verdict `done` via `pi` / `deepseek` / `deepseek-v4-pro:high`; the operator-created smoke Issue parked in `in_review` as expected [source: wiki/raw/sessions/2026-07-05-pi-rmm-binding-onboard.md#durable-facts].

## Safety note

No top-level `CLAUDE.md` or `AGENTS.md` was present during onboarding. For `type: coding`, this is a warning only: Symphony skips `WORKFLOW.md`, and repo safety/conventions remain the bound repo's responsibility [source: wiki/raw/sessions/2026-07-05-pi-rmm-binding-onboard.md#open-questions-and-follow-ups].

## Related

- [binding-symphony](binding-symphony.md) — another local coding binding.
- [symphony-skills-index](../analyses/symphony-skills-index.md) — operator skill suite covering binding scaffold/restart/smoke.
