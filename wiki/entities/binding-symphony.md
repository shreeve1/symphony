---
title: symphony Binding
type: entity
status: promoted
created: 2026-06-13
updated: 2026-06-13
sources:
  - bindings.yml
  - skill_migration.py
  - WORKFLOW.md
  - wiki/raw/sessions/2026-06-13-symphony-self-binding-scaffold.md
confidence: high
tags: [binding, symphony, self-binding, podium, coding, default-agent, pi, scaffold]
---

# symphony Binding

Third live Project Binding, created 2026-06-13 via `symphony-binding-scaffold`. It is a **self-binding**: `repo_path` points at the Symphony scheduler's own source repo (`/home/james/symphony`), so Issues dispatched here let agents inspect, edit, and land commits against the code of the service that runs them.

## Configuration

| Field | Value |
|---|---|
| `name` | `symphony` |
| `type` | `coding` |
| `tracker` | `podium` |
| `repo_path` | `/home/james/symphony` |
| `base_branch` | `main` |
| `default_agent` | `pi` |
| `approval.enabled` | `false` |
| `landing.mode` | `local` |
| `plane_project_id` | `symphony` (transitional config-compat only; not a Plane call) |

Podium side: a `binding` row (`name='symphony'`, `display_name='Symphony'`, `archived=0`) plus a `binding_settings` row (`context_compact_threshold_tokens=16000`, `keep_recent_runs` default) in the live `/home/james/symphony/podium.db`. No Plane API or `plane_adapter` involvement (Binding-is-Project; Podium treats the binding itself as the project).

## Risk posture

Highest-risk of the three live bindings. `landing.mode: local` commits straight into the scheduler repo, and a coding dispatch could modify the running service's own source. The existing `homelab` and `trading` bindings deliberately target *other* repos. Monitor any Run against `symphony`.

Because the binding is `type: coding`, dispatch resolves `is_coding` correctly per-binding (`scheduler.py:948`) even though `homelab` (`infra`) is the first entry in `bindings.yml` — the old first-binding-wins bug (C-0066) is fixed.

## WORKFLOW.md (commit `2e8ff42`, hardened `a3f0fa5`, 2026-06-13)

Per-repo policy authored via `symphony-workflow-author`, render-tested against `prompt_renderer.py`. Thin-engine v2, frontmatter `poll_interval_ms=30000` / `run_timeout_ms=3600000`, always-`review` completion (never auto-close). Operator chose **edit-and-commit-to-`main`** autonomy over the scheduler's own source (same posture as `trading`/`homelab`). A **Live-Infrastructure Safety Boundary** keeps these operator-gated regardless of commit freedom: service restart / unit edits, and mutating `bindings.yml`, `podium.db`, the Plane API, or worktrees. Read from disk per-dispatch, so it is effective without a restart.

A gap-review pass (`a3f0fa5`) added three self-binding guards: (1) never start a scheduler instance yourself (`python -m main` would default its lock to repo-local `.symphony.lock`, not the live lock, and become a rogue second poller/dispatcher); (2) the repo-root `podium.db` IS the live database via `resolve_db_path()` fallback, so naive `connect()`/scripts hit live rows; (3) a self-modification gate requiring explicit issue approval + review callout before editing `WORKFLOW.md`, `bindings.yml`, or the `symphony-*` operator skills.

## Status / follow-ups

- Binding is live in the running scheduler since the 2026-06-13 restart (`symphony_started … bindings=3`, `reconcile_startup_done binding=symphony`).
- `WORKFLOW.md` authored and committed (`2e8ff42`) — no longer a stub, so `symphony-binding-smoke` will run.
- Remaining optional: harden `_append_binding` against `bindings.yml` comment loss (C-0171).

## Related

- [binding-homelab](binding-homelab.md), [binding-trading](binding-trading.md) — sibling live bindings.
- [analysis-session-symphony-self-binding-scaffold](../analyses/analysis-session-symphony-self-binding-scaffold.md) — the session that created it and hardened the scaffold skill.
