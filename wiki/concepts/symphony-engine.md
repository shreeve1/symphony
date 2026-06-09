---
title: Symphony engine
type: concept
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - wiki/raw/symphony-context.md
confidence: high
tags: [engine, dispatch, architecture, core]
---

# Symphony engine

Symphony is the scheduler that polls a Plane project for candidate issues, dispatches each to a coding agent against a bound git repo, and posts the agent's results back to the issue [source: wiki/raw/symphony-context.md#3]. One engine, many projects.

## Core loop

`poll Plane → select candidate issue → render prompt → dispatch to agent → comment results back` [source: wiki/raw/symphony-context.md#8].

## Iteration unit

Symphony iterates over **Project Bindings**. A Binding ties one Plane project to one git repo plus its dispatch config. A Binding carries [source: wiki/raw/symphony-context.md#11-12]:

- `plane_project_id` and its Tracker Contract (Role→name+UUID mapping)
- repo path and base branch
- `default_agent` (`pi` or `claude`); per-issue `agent:claude` / `agent:pi` label overrides it
- approval-gate policy — opt-in, default off; homelab opts in
- Landing policy — default `local`

All Bindings share one workspace-scoped Plane API key for the single `homelab` workspace, differing only by `plane_project_id` [source: wiki/raw/symphony-context.md#12].

## Mode (work kind, label-resolved)

Mode is resolved from an issue's Plane labels. Current values: **plan** (produce a reviewable plan artifact, no production changes), **build** (execute an already-approved plan), **execute** (default; routine change) [source: wiki/raw/symphony-context.md#16].

Mode is split across two layers [source: wiki/raw/symphony-context.md#16]:

- Engine owns Mode as *mechanism*: resolves Mode from labels, exposes it to the renderer as a prompt variable, uses it for the side-effect backstop (plan→artifact written, build→commit present) and Plane-state defaults.
- Workflow owns what each Mode *means* as instruction for the repo.

Fixed mode set and side-effects live in the engine; the work each mode entails lives in the bound repo's `WORKFLOW.md`.

## Agent (the coding tool)

The tool Symphony shells out to. Today **pi** (one-shot subprocess); generalizing to also include **claude** (tmux send-keys session) [source: wiki/raw/symphony-context.md#20]. Each agent has its own dispatch shape, isolated behind an **Agent Adapter** [source: wiki/raw/symphony-context.md#35-36].

## Workflow (per-repo prompt policy)

`WORKFLOW.md` at the bound repo's root. Mandatory: a Binding whose repo has no readable `WORKFLOW.md` is a hard config error — Symphony refuses to dispatch, skips the issue, and posts a blocked comment naming the missing file [source: wiki/raw/symphony-context.md#24]. No built-in fallback policy.

The agent self-selects relevance from the issue's labels rather than Symphony selecting prompt fragments by label. Symphony's renderer is pure mechanism (variable substitution, issue/comment escaping, schedule block); the Workflow supplies all repo-specific instruction.

## Tracker abstraction

The **Tracker Adapter** isolates Plane-specific API calls behind one interface, so the engine talks to "a tracker" rather than Plane directly. Keeping Plane today; the seam makes a future move to another tracker (e.g. GitHub Issues) a one-adapter swap instead of an engine rewrite [source: wiki/raw/symphony-context.md#28].

The **Tracker Contract** is the per-Binding mapping from engine-facing **Roles** to a project's concrete labels and states (names plus per-project UUIDs). Roles include `mode:plan`, `mode:build` (execute is the absence of both), `agent:*`, `approval-required`, `approved`, `scheduled`, and the five states (Todo / In Review / Running / Blocked / Done) [source: wiki/raw/symphony-context.md#32]. A Role a Binding omits simply disables that behaviour.

## Run, Run Worktree, Verdict

- **Run**: a single dispatch of one issue to one agent — the unit a Verdict describes [source: wiki/raw/symphony-context.md#48].
- **Run Worktree**: the isolated git worktree-plus-branch Symphony creates per Run, so concurrent Runs (even against the same repo) never share a working tree. Created at dispatch, torn down after the Verdict is reconciled [source: wiki/raw/symphony-context.md#52].
- **Verdict**: outcome of a single dispatch, declared by the agent via `SYMPHONY_RESULT:` line, value one of **done** / **review** / **blocked**, mapping to Plane states Done / In Review / Blocked. Last occurrence wins; unknown/absent falls through to a heuristic. Agent may also emit `SYMPHONY_SUMMARY:` for the human-readable Plane comment. For claude (tmux), lines are scraped from the pane before the Done Marker, backstopped by post-run side-effect inspection [source: wiki/raw/symphony-context.md#44].
- **Done Marker**: per-run nonce string the agent prints when finished, letting Symphony detect completion of a tmux session with no exit code [source: wiki/raw/symphony-context.md#40].

## Landing (branch reconciliation)

Converging a completed Run's branch back into the repo's base branch. Default is **local**: Run Worktree torn down but branch ref kept, committed and unpushed, to be merged by hand (the rpiv-merge pattern). Symphony never auto-pushes or auto-merges by default; per-Binding policy can opt into push/PR or auto-merge; homelab/infra Binding stays local [source: wiki/raw/symphony-context.md#56].

## Relationships

- A Project Binding maps one Plane project to exactly one repo
- An issue carries one Mode (resolved from labels)
- Symphony dispatches an issue to one Agent as one Run
- Each Run executes in its own Run Worktree; a global cap bounds how many Runs are live at once
- A finished Run's branch is reconciled by Landing (default local/manual) [source: wiki/raw/symphony-context.md#65-69]

## Vocabulary to avoid

Per CONTEXT.md `_Avoid_:` lines: "the bot", "the runner", "workspace" (when meaning Binding), "task type", "stage", "model" (when meaning Agent), "domain overlay", "Plane client" (when meaning Tracker Adapter), "the labels" (when meaning Role), "domain labels", "runner" (when meaning Agent Adapter), "sentinel" (use Done Marker), "ok/failed" / "exit status" (when meaning Verdict), "job" (when meaning Run), "workspace"/"checkout" (when meaning Run Worktree), "deploy"/"PR" (when meaning Landing), "template" (when meaning Project Scaffold).
