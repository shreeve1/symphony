---
id: 007
title: bindings.yml multi-project config
status: done
blocked_by: [1, 2]
updated: 2026-06-05
actor: ralph
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

- [x] `bindings.yml` loads into a list of binding objects at startup.
- [x] A binding resolves its contract, repo+base branch, default_agent, approval policy (default off), and landing policy (default local).
- [x] Secrets (Plane API key) are read from env, never from the yaml.
- [x] A missing required binding field is a clear config error naming the field.
- [x] The engine iterates all bindings (homelab is just one entry); single-binding behavior preserved.
- [x] Suite green, including a multi-binding load test.

## Verification

`uv run pytest`

## Blocked by

- Blocked by #1
- Blocked by #2

## Implementation Notes

Resolved the review blocker by relying on the #009 `RoutingAgentAdapter` for `default_agent: claude` and per-issue `agent:claude` / `agent:pi` overrides, moving approval-required candidate filtering out of the Plane adapter and into scheduler policy checks, and making plan-mode approval-required labels opt-in on the binding approval policy. Added regression coverage for default-off approval dispatch, opt-in approval holds, plan label behavior, and poller approval-label pass-through.

Verification: `uv run pytest` passed (385 tests). Critical LSP diagnostics for `main.py`, `plane_adapter.py`, `scheduler.py`, `tests/test_plane_poller.py`, and `tests/test_scheduler.py` reported no diagnostics. Mandatory fresh review returned `RALPH_REVIEW: PASS_WITH_NOTES`.
