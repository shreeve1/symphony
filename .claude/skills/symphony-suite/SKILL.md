---
name: symphony-suite
description: Index of Symphony skills for project onboarding, service restarts, binding status checks, smoke tests, and Plane recovery workflows.
disable-model-invocation: true
---

# Symphony Skill Suite

Cat this file to remember which `symphony-*` skills exist and what they do. Skills live at `~/dotfiles/.claude/skills/<name>/SKILL.md` and are symlinked into `~/.claude/skills/`.

## Daily operations

- **symphony-bindings-status** — read-only "what's running" table. Run first; no mutations, no env file reads. Good before any restart, scaffold, or smoke.
- **symphony-troubleshooter** — real-time diagnostic copilot. Captures safe context, reviews logs with James, correlates bindings/issues/runs, ranks hypotheses, and hands mutations to restart/smoke/recover skills.
- **symphony-restart** — pre-sanity → ask → `sudo systemctl restart` → verify reconcile + dispatch log lines. `--with-tests` re-runs pytest in sanity (off by default).

## Onboarding a new repo (in order)

1. **symphony-project-scaffold** — create Plane project + binding entry. Dry-run preview; live mutation requires typed slug.
2. **symphony-workflow-author** — interview-driven WORKFLOW.md authoring at the bound repo root. Refuses live boundaries without a sandbox-detection answer. Ships with `generic-app` template; `trading-sandbox` / `infra-rmm` / `data-pipeline` deferred until a concrete second template is needed.
3. **symphony-restart** — pick up the new binding.
4. **symphony-binding-smoke** — file a low-risk smoke ticket, watch one Run, report `SYMPHONY_RESULT`. Persists ticket by default; `--archive-on-success` opts in.

The **symphony-onboard-project** umbrella chains those four with a checkpoint between each step. No umbrella-level dry-run — each sub-skill still owns its own gate.

## Recovery

- **symphony-plane-recover archive `<project>`** — archive a half-built Plane project. Typed-slug gate.
- **symphony-plane-recover state-fill `<project>`** — idempotently add the standard state set (Todo / In Review / Running / Blocked / Done) and label set (mode:plan, mode:build, approval-required, agent:claude, agent:pi). Useful when scaffold partially completed or when adopting a legacy project.

## Teardown a binding (inverse of onboarding)

- **symphony-binding-remove** — drop a binding's `bindings.yml` entry and either **archive** (default, reversible — `binding.archived = TRUE`, keeps Issue/Run history) or **purge** (destructive — deletes the binding's Runs/Issues/settings rows). Purge requires explicit confirmation of the Issue/Run counts. Inverse of `symphony-binding-scaffold`.
- **symphony-offboard-project** umbrella chains `symphony-bindings-status` → `symphony-binding-remove` → `symphony-restart` with a checkpoint between each step. Archive by default; purge stays gated. Inverse of `symphony-onboard-project`.

## Ownership boundaries

- `bindings.yml` entries are written only by the scaffold/remove pair (`symphony-binding-scaffold` adds, `symphony-binding-remove` removes); `symphony-project-scaffold` is the deprecated Plane-era alias. Other skills read it but never mutate.
- The `symphony-host.service` unit file is touched only by James directly; `symphony-restart` runs the unit but never edits it.
- Plane mutations always require explicit James approval at the moment, even inside the umbrella. No skill auto-rollbacks.
