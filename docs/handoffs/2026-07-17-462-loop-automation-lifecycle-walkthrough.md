# Handoff — Walk the loop-automation lifecycle to find gaps/improvements

## Goal for the next session

The operator (James) wants a **guided walkthrough of the loop automation
lifecycle**, end to end, so we can jointly spot **gaps and improvement
opportunities**. This is an interactive teaching + design-critique session, not
an implementation task. Do not start editing code — walk the operator through
each stage, stop at each transition, and surface risks/edge cases as you go.

Suggested skill to start with: **`teach`** (guided walkthrough), or **`grill-me`
/ `grill-with-docs`** if the operator wants to turn the identified gaps into a
sharpened design. Start read-only.

## Context: how we got here (Podium issue #462)

Issue #462 was originally "the create-automation card is missing skill/agent/
model options." Over several slices we: made those pins inline (dropped the
"Advanced pins" toggle), added dispatch-safety guards (agent-filtered models,
model-driven effort list, empty-skill hint), and switched the Interval field to
minutes. All landed + deployed. Commits: `5af1b30`, `9883903`, `00fd658` on
`main`. The lifecycle walkthrough is a **follow-on** the operator asked for after
those shipped — the automations UI is now fully exposed, so it's a good moment to
audit the runtime behavior behind it.

There are **two automation modes** — `spawn` (recurring interval, fires N issues)
and `loop` (single evolving issue that re-dispatches until a completion marker or
iteration cap). The operator specifically asked about the **loop** lifecycle.

## Authoritative references — read these first, don't re-derive

- **ADR-0038** `docs/adr/0038-binding-scoped-automations-spawn-and-loop.md` —
  the accepted design: spawn vs loop semantics, why loops use a persistent
  worktree, provenance (`origin='automation'`), relation to one-shot scheduling.
- **ADR-0040** `docs/adr/0040-automation-pin-fields.md` — the per-automation
  skill/agent/model/effort/base_branch/worktree pin fields (issue #459/#461).
- Pure helpers: `automation.py` — `count_loop_iterations`, `loop_iteration_marker`
  (`### Symphony Loop Iteration · N`), `loop_instructions`, `LOOP_COMPLETE_PREFIX`,
  `LOOP_CAP_PREFIX`, `compute_next_fire`, `render_template`.
- Loop engine: `tracker_podium.py` `reconcile_loop_automations` (~line 712) — the
  heart of the loop lifecycle. Spawn engine: `fire_due_spawn_automations` (~632).
- Scheduler wiring: `scheduler/loop.py` `run_loop` (~92) calls
  `_reconcile_loop_automations` (~167); `scheduler/reconcile.py`
  `reconcile_loop_automations` (~98) is the adapter-agnostic seam.
- Model resolution gate (fire-time failure mode): `model_catalog.py`
  `resolve_model` (~97-130) raises `ModelResolutionError`.
- UI: `web/frontend/app/[binding]/automations/page.tsx`; API/DB:
  `web/api/automations.py`, `web/api/schema.py` (`automation` table).

## The loop lifecycle, as currently implemented (verified this session)

Trace it in `tracker_podium.py::reconcile_loop_automations`, called each tick:

1. **Create (first iteration).** For each enabled `mode='loop'` automation with
   no existing issue at `external_id = automation:<id>:loop`: insert one issue.
   Title/body get `{binding}` substitution; body appends `loop_instructions(marker)`.
   Pins threaded in; `worktree_active` **hard-coded True** (loops require a
   persistent worktree — operator-confirmed 2026-07-17); `reasoning_effort`
   defaults to `high`; `auto_land=False`; `origin='automation'`;
   `comments_md = loop_iteration_marker(1)`.
2. **Wait.** If the issue exists but `state != 'in_review'`, skip (agent still
   working / dispatched).
3. **Terminate check** (issue is `in_review`): count iterations from comment
   markers; if `completion_marker_exists(issue_id, marker)` -> append
   `LOOP_COMPLETE_PREFIX` block; elif `iterations >= cap` -> append
   `LOOP_CAP_PREFIX` block ("worktree preserved for operator review"). Either
   terminal path **disables the automation** (`enabled=0`).
4. **Advance** (no terminal condition): append `loop_iteration_marker(N+1)`, flip
   issue `state='todo'` (re-dispatch), bump `updated_at`.

The single evolving issue + worktree is the loop's only memory; each iteration
starts with fresh agent context (see `loop_instructions`).

## Candidate gaps/improvements to probe with the operator (starting list — verify each live before asserting)

These are hypotheses from this session's read; the next session should confirm
each against the code before presenting as fact (the `grill-with-docs` fact-check
discipline applies).

- **No error/stall handling in the loop.** If an iteration's run fails, times
  out, or the issue lands in `blocked`/error rather than `in_review`, the loop
  reconciler only advances on `in_review`. Does a failed iteration wedge the loop
  forever? Is there a max-consecutive-failure cutoff? (Contrast spawn's cadence.)
- **Cap semantics.** `iterations >= cap` uses comment-marker count. Off-by-one
  worth checking (marker for iteration 1 written at create; is the cap inclusive?).
- **Completion detection.** `completion_marker_exists` — where does it look
  (worktree path?), and what happens if the worktree was cleaned up or the marker
  filename collides with repo content?
- **Disable-on-terminal is permanent.** Both complete and cap-reached set
  `enabled=0`. Is there a re-arm path, or must the operator recreate? Is that the
  desired UX?
- **Pin drift mid-loop.** Pins are copied into the issue at create only. Editing
  the automation's model/agent after loop start has no effect (and could confuse).
  Also `resolve_model` can still fail at *dispatch* even though the UI guards
  creation — worth confirming the loop surfaces that clearly vs. silently wedging.
- **worktree lifecycle / cleanup.** Loops preserve the worktree on cap; who
  reaps it? Interaction with `prune_run_logs` and stale-worktree cleanup.
- **Interval field is spawn-only.** Loops have no interval (they re-dispatch on
  completion); confirm the UI hides interval for loop mode and that's clear.

## State of the tree

`main` is clean re: #462 work (all committed + pushed + deployed). There are
unrelated uncommitted files in the working tree (`bindings.yml`, `.gitignore`,
`plans/.patrol-*.state.yml`, `wiki/*`, graphify artifacts) — **not ours**, leave
them alone. This session was a Podium slice run (ADR-0028): no `wiki/` edits.

## Working notes

- Frontend deploy = `web/frontend/deploy.sh` (build->atomic swap->restart
  `podium-web.service`). Loop-lifecycle changes would be **backend** (Python) —
  those need a `symphony` scheduler restart, not the web deploy.
- Git remote is `origin` but uses the `github-personal` SSH host alias (push:
  `git push origin HEAD:main`).
