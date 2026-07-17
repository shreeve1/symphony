---
status: accepted
relates-to: ADR-0009 (session resume), ADR-0014 (operator-gated worktree landing), ADR-0018 (one-shot scheduling), ADR-0023 (provenance-gated auto-land), ADR-0028 (slice/wiki boundary)
decided-with: James, 2026-07-16 (Podium issue #442 grill; captured in GitHub issue #2)
---

# Binding-scoped Automations have distinct spawn and loop modes

## Context

Symphony scheduling is one-shot: an Issue may wait until `scheduled_for`, then the
schedule is cleared when it dispatches. The infra patrol cron recurs, but operators
cannot author it in Podium. This leaves two different needs unsolved:

- repeat a template on a time interval, with an independent Issue for every fire;
- grind on one coding task through bounded, fresh-context passes while preserving
  filesystem progress.

Treating both as Issue recurrence would mix incompatible identity, memory, trigger,
and termination rules. Reusing ADR-0009 Session Resume for the second need would
also violate the fresh-context requirement, while automatically landing its result
would bypass ADR-0014's operator gate and ADR-0023's narrow `auto_land` exception.

## Decision

Add **Automation** as a first-class, binding-scoped entity with its own table and
operator management surface. It is not a property of an Issue and does not change
the Issue lifecycle. An Automation has one of two deliberately distinct modes.

### Spawn mode

Spawn mode is time-triggered and available to every binding. Each fire mints a
brand-new Issue from the Automation's title/body template. Every occurrence has its
own identity, Run history, Comments, and terminal state, with provenance linking it
back to the Automation.

A simple stored interval determines the next fire. A finite occurrence count
disables the Automation after its final fire; an unlimited Automation continues
until disabled. Firing advances the Automation independently of prior spawned
Issues, so a stuck occurrence does not halt later ones. Spawned Issues enter the
normal binding candidate and concurrency rules.

### Loop mode

Loop mode is completion-triggered: one Automation drives repeated Runs of one Issue,
starting the next iteration only after the previous iteration finishes. It is
available in v1 only when the binding supports a persistent active per-Issue
worktree. In practice this is a subset of coding bindings; remote coding bindings
that force worktrees off are ineligible. The API rejects, and Podium hides, loop
mode when that prerequisite is unavailable.

Every iteration starts a fresh agent context. The loop dispatch path deliberately
bypasses both ADR-0009 native Session Resume and its Comments/Context re-feed floor.
It renders the static Issue task and loop instructions again, but carries no prior
Run conversation. This is distinct from ADR-0014 commit redispatch, which preserves
continuity so an agent can finish the same turn of work.

The persistent per-Issue worktree is the loop's only carried memory. Agents may
record progress there (for example in `PROGRESS.md`); no new conversation store or
per-Issue iteration-counter column is introduced. Iterations are counted from a
stable marker in Issue Comments, following the existing commit-redispatch counting
pattern.

Between iterations Symphony checks the configured **Loop Completion Marker** file
in the worktree (`DONE.md` by default). This loop-lifecycle marker is distinct from
the per-Run Done Marker defined in `CONTEXT.md`. The loop terminates when either:

1. the Loop Completion Marker exists; or
2. the configured iteration cap is reached.

Both termini park the Issue in `in_review`. Cap exhaustion adds a clear cap-reached
Comment. Neither path sets `done` or invokes `auto_land`, even for an Issue carrying
ADR-0023 provenance: the operator reviews and performs the normal ADR-0014
fast-forward landing. Partial work therefore remains inspectable and is never
silently discarded.

## Contract summary

| Property | Spawn | Loop |
|---|---|---|
| Trigger | Time interval | Prior iteration completion |
| Issue identity | New Issue per fire | One Issue throughout |
| Carried memory | None between independent Issues | Persistent worktree only |
| Stop condition | Finite count exhausted or disabled | Loop Completion Marker found or iteration cap |
| Binding support | All bindings | Persistent-worktree-capable coding bindings |
| Terminus | Each Issue follows normal lifecycle | Always `in_review`; operator lands |

## Consequences

- Podium gains one canonical per-binding Automations surface rather than a second
  recurrence model in the Issue editor.
- Spawn recurrence coexists with ADR-0018 one-shot Issue scheduling without changing
  its comment grammar or `scheduled_for` semantics.
- Loop dispatch needs an explicit non-resuming, non-refeeding path. Future changes to
  continuity must preserve that exception.
- Loop work may span many Runs but cannot run forever, and no loop terminus can merge
  unattended.
- Implementation slices follow ADR-0028: dispatched slices record rationale in their
  issue comments and do not edit `wiki/`; one consolidated operator pass updates the
  wiki after the batch lands.

## Out of scope

- Loop mode for infra bindings or any binding without a persistent per-Issue
  worktree.
- Cron or rrule syntax; spawn v1 stores only a simple interval.
- Accumulating-context loop variants.
- Autonomous landing of loop work.
- Migrating the existing infra patrol cron.
