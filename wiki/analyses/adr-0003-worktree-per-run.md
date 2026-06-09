---
title: ADR-0003 — Worktree-per-run with global concurrency cap
type: decision
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - wiki/raw/adr-0003-worktree-per-run.md
  - docs/adr/0003-worktree-per-run-with-global-concurrency-cap.md
confidence: high
tags: [adr, concurrency, worktree, run, plan-build-handoff, reconcile]
---

# ADR-0003 — Isolate each run in a git worktree, bounded by a global concurrency cap

## Problem

Symphony today serializes all work behind one global `fcntl` flock — at most one Run executes at a time, against the single shared checkout of the bound repo. Generalizing to many projects, and the explicit requirement to have **multiple agents working the same repo at the same instant**, breaks that model: two concurrent Runs cannot share one working tree without corrupting each other's edits, staging, and branch state [source: wiki/raw/adr-0003-worktree-per-run.md#3].

## Decision

**Worktree-per-run plus a global concurrency cap.** Each Run gets its own `git worktree` on a fresh branch, created at dispatch and torn down after its Verdict is reconciled. The per-Run isolation is what makes same-repo parallelism safe. A global cap (initially 2–3) bounds total live Runs across all projects so the host isn't swamped — replacing the old single-flock serialization, not layering on top of it [source: wiki/raw/adr-0003-worktree-per-run.md#5].

A per-project serial lock briefly considered is rejected precisely because it would forbid the same-repo concurrency that motivated this.

## Two mechanics this implies

**1. Cap is necessary but not sufficient.** Today a tick acquires a single per-tick `fcntl` flock and dispatches exactly one issue (`run_tick` returns one issue/mode). Same-repo parallelism requires restructuring the tick into a **concurrent dispatcher** that launches and supervises N in-flight Runs as async tasks; the per-tick flock is *replaced by a live-run semaphore* bounding that set, not merely deleted [source: wiki/raw/adr-0003-worktree-per-run.md#7].

**2. Symphony keeps no database**, so the cap count and the live-Run set are in-memory and are lost on a `symphony-host.service` restart — leaving orphaned worktrees and detached tmux sessions that wedge the repo exactly as feared, and (for the tmux-claude path) no process to signal on timeout. So startup must **reconcile live state from durable signals** — existing `git worktree` entries, per-run-named tmux sessions, and Plane issues left in the Running state — and a reaper must clean up orphans. Requires a deterministic `run-id → worktree path / branch name / tmux session` naming scheme defined up front [source: wiki/raw/adr-0003-worktree-per-run.md#7].

## Staged pipeline deferred

A Run executes as one autonomous pass for now. The staged-pipeline shape (research → design → plan → implement → validate → commit, agents handing off one stage at a time, as `rpiv-run` does) is deliberately deferred: it reuses the same Run Worktree later without changing this isolation model. `rpiv-run` is the precedent for staging inside one Run; the concurrency precedent is the worktree-per-agent pattern proven in Composio's orchestrator and in rpiv's branch-per-run landing step [source: wiki/raw/adr-0003-worktree-per-run.md#9].

## Accepted costs

Worktree lifecycle: creation and guaranteed cleanup (including after crash/timeout, or orphaned worktrees wedge the repo), unique branch per Run, per-run tmux session/cwd keying so two claude runs don't collide, disk cost of N working copies. The `_auto_commit` backstop now commits to the Run's own branch rather than the shared checkout [source: wiki/raw/adr-0003-worktree-per-run.md#11].

How those per-Run branches converge back to the base branch (push + PR vs. local-only manual landing) is a separate decision, not settled here — see CONTEXT.md `Landing` entry.

## Plan → build artifact handoff (settled here)

Worktree isolation breaks an existing mechanism: today a `plan` Run writes `plans/<slug>.md` into the shared checkout and a later `build` Run reads it back. Under worktree-per-run with local landing, the plan Run's artifact lives on an ephemeral branch that is torn down and (by default) never merged, so a build Run branched off base would never see it [source: wiki/raw/adr-0003-worktree-per-run.md#13].

Resolution: a **git-ref handoff** — the plan-handoff comment records the plan Run's *branch ref* rather than an absolute filesystem path, and the build Run creates its worktree off that plan branch instead of base. Keeps the handoff entirely in git (no carve-out in worktree isolation, no Symphony-side artifact store), is consistent with local landing — the plan branch is kept like any other — and reuses the existing handoff-comment plumbing (`_PLAN_HANDOFF_MARKER`, `_plan_path_from_comments`), changing only the payload it carries. The plan artifact rides along on the branch, so the build worktree still finds `plans/<slug>.md` where the path validator expects it.

## Related

- [ADR-0002](adr-0002-generalize-symphony.md) — adapter seams this composes with
- [Symphony engine](../concepts/symphony-engine.md) — Run, Run Worktree, Landing sections
