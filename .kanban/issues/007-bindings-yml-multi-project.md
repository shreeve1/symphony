---
id: 007
title: bindings.yml multi-project config
status: in-progress
blocked_by: [1, 2]
updated: 2026-06-04
parent: null
priority: 0
created: 2026-06-04
---

## What to build

Replace the single-binding env singleton (`config.py` `SymphonyConfig.from_env`)
with a `bindings.yml` describing N Project Bindings. Each binding carries:
`plane_project_id` + its Tracker Contract (#001), repo path + base branch,
`default_agent` (pi|claude) with per-issue `agent:claude`/`agent:pi` override,
the approval-gate policy (opt-in, **default off**), and the Landing policy
(**default local**). All bindings share one workspace-scoped Plane API key; secrets
stay in env and are never read from the yaml. The engine iterates bindings.

See the **Project Binding** and **Landing** glossary entries in `CONTEXT.md`.

## Acceptance criteria

- [ ] `bindings.yml` loads into a list of binding objects at startup.
- [ ] A binding resolves its contract, repo+base branch, default_agent, approval policy (default off), and landing policy (default local).
- [ ] Secrets (Plane API key) are read from env, never from the yaml.
- [ ] A missing required binding field is a clear config error naming the field.
- [ ] The engine iterates all bindings (homelab is just one entry); single-binding behavior preserved.
- [ ] Suite green, including a multi-binding load test.

## Verification

`uv run pytest`

## Blocked by

- Blocked by #1
- Blocked by #2
