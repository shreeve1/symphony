---
status: proposed
relates-to: ADR-0005 (replace Plane with Podium; Binding-is-Project), ADR-0003 (per-binding semaphore concurrency)
context: when many issues are created at once Symphony dispatches them in parallel, but there is no way to express that some must wait for others
decided-with: James, 2026-06-23 (Podium Issue #102 "Tralph"; pivoted off start/stop/control — operator drives the loop via issues — to "we need dependency and parallelization")
supersedes: the never-built pause/start-stop design previously drafted for this issue (no code landed)
---

# Enforced issue dependencies + dependency-gated parallel dispatch

## Context

Issue #102 began as "bring the `tralph` loop into Podium." Through two operator
replies it narrowed: **start/stop/control is not wanted** (the operator drives
the loop by creating issues). The real requirement is the previously-deferred
tralph-fidelity gap: *"when issues are all created at the same time they are
picked up and worked in parallel — great if they can be worked in parallel, but
we need some sort of dependency and parallelization."*

Current reality:

- **Parallelization already exists.** Each binding's `run_loop` dispatches under
  an `asyncio.Semaphore(config.run_cap)` (`scheduler/__init__.py`
  `_effective_run_cap`). `run_cap` defaults to **2** (env `SYMPHONY_RUN_CAP`);
  remote bindings are forced to 1. So up to `run_cap` `todo` issues run at once —
  exactly the parallel pickup the operator observed.
- **Dependencies do not exist.** The Podium `issue` table has no
  `blocked_by`/`depends_on` column. `web/cli/podium_issues.py` (line 17) states
  it outright: the `.kanban` `blocked_by` frontmatter "survives only as text
  inside the issue description (advisory, not gated)." `tracker_podium`
  dispatches every `todo` issue `ORDER BY created_at, id` with no gating.

So parallelism is solved; **enforced dependency ordering is the gap.** Adding it
turns "all N issues run at once" into "independent issues run in parallel (up to
`run_cap`), dependents wait for their blockers."

## Decision

1. **Persist dependencies.** Add `blocked_by` to the Podium `issue` table as a
   JSON array of Podium issue ids, mirroring the `.kanban` frontmatter shape
   (`blocked_by: [99]`). Alembic migration `0010`.
2. **Gate dispatch on dependencies.** A `todo` issue is eligible only when every
   id in its `blocked_by` resolves to an issue in `done` or `archived`. Gated
   issues **stay `todo`** — they are NOT flipped to the `blocked` state.
   (`blocked` already means an agent-raised failure; conflating the two would
   corrupt status semantics and the blocked-reconciler.) Eligible independent
   issues dispatch up to `run_cap` → automatic parallelization; a dependent
   becomes eligible on the tick after its last blocker closes.
3. **Carry dependencies through the write paths.** `podium_issues.py` and the
   create/patch API persist `blocked_by`, translating local kanban ids → the
   Podium issue ids assigned on insert.
4. **Parallelization knob stays `run_cap`.** No new mechanism; the existing
   `SYMPHONY_RUN_CAP` (default 2) tunes max concurrency. Per-binding override is
   deferred (see below).

## Design choices

- **JSON column, not a join table.** Matches the kanban source format, suits the
  single-user / dozens-of-issues scale, and makes both the mirror and the
  eligibility check trivial. A relational dependency table + integrity machinery
  is YAGNI here.
- **Gated-todo stays `todo`.** Keeps "waiting on a dependency" distinct from
  "agent failed." Only candidate *selection* is filtered; no state transition.
- **Unresolved blocker id ⇒ treated as satisfied (with a logged warning).** A
  typo or cross-binding reference must not wedge an issue forever. A true cycle
  (a→b→a) is rejected at write time (cycle check in the mirror/create path)
  rather than relying on this rule.

## Consequences

- Independent issues created together still parallelize (up to `run_cap`);
  dependents serialize correctly without operator babysitting.
- Hard-to-reverse step: Alembic `0010` on the **live** Podium DB + a
  `symphony-host` restart to pick up the eligibility gate — sequenced as a gated
  MANUAL slice.

## Out of v1 / deferred

- **Per-binding parallel cap** (`binding_settings.max_parallel` overriding
  `run_cap`) — offer only if the global knob proves too blunt.
- **Editing dependencies in the UI** — v1 ships a read-only "waiting on #N" chip;
  dependencies are authored in `.kanban` / via the API.
- **Priority-ordered selection** (Podium has a `priority` column but selects
  FIFO) and **fresh-session review-after-DONE** — separate gaps, not this issue.

## Alternatives considered

- **Join table for dependencies** — more "correct" relationally; rejected as
  overkill at this scale.
- **Keep `blocked_by` advisory + rely on insertion/created_at order** — today's
  behavior; rejected because parallel dispatch ignores order, which is exactly
  the failure the operator hit.

## Update 2026-06-23 — corrected constraint (dependency-gating is necessary but NOT sufficient)

A third operator reply reframed the problem: *"it's not just dependency... it's
which ones can run at the same time without conflicting with each other's work in
the same tree."* Investigation confirmed the real root cause:

- `scheduler/__init__.py` `_dispatch_cwd` runs an agent **directly in the shared
  `repo_path`** unless the issue has `worktree_active` (opt-in, **off by
  default**). `_effective_run_cap` gives local coding bindings `run_cap` (=2).
- So two `todo` issues dispatched concurrently `cd` into the **same** working
  tree and interleave uncommitted edits / the git index. **Any** two concurrent
  shared-tree coding runs conflict — independent or not. The "parallelism already
  works" claim above holds only for worktree-isolated runs.

Therefore safe parallelism needs **three** layers, not one:

1. **Isolation (enabler).** You cannot safely run two coding agents in one shared
   tree. Either serialize (cap 1) or give each concurrent run its own worktree
   (machinery exists — ADR-0003/0014 — currently opt-in per issue).
2. **Dependency ordering** (this ADR) — B waits for A.
3. **Mutual exclusion / resource constraint** (NEW, unspecified) — even isolated,
   two parallel runs that edit the same files collide at merge; issues need a way
   to declare "these can't co-run" (a resource/lock key; same key ⇒ serialized).

**Open fork (operator decision pending):**

- **(P1) Safe floor — serialize shared-tree coding.** Make `_effective_run_cap`
  return 1 when the binding/issue is not worktree-isolated (mirrors the existing
  remote-binding rule). One small change; eliminates every conflict immediately;
  cost: no parallelism until worktrees are enabled.
- **(P2) Real parallelism — worktree-per-run default + mutex/resource layer.**
  Isolate each run, keep dependency ordering, and add a co-run exclusion key so
  parallel runs don't collide at merge. Bigger; delivers conflict-free parallel.

Recommendation: ship **P1** as the immediate safety fix, then layer dependency
(this ADR) + **P2** for opt-in real parallelism. The dependency slices 105-109
remain valid and compose with either path. A follow-up ADR will specify the
mutex/resource model once the operator picks the parallelism target.

## Update 2026-06-23 (2) — operator chose P2; fork resolved, architecture converged

Operator picked **P2 — real conflict-free parallelism** (skip the P1 serialize
floor). This ADR now folds the mutex/resource model in directly rather than
deferring to a follow-up. Three layers ship together:

### Layer 1 — Isolation (the enabler): worktree-per-run by default

Today `_worktree_run_fields` (`scheduler/__init__.py:385`) returns `{}` unless the
candidate has `worktree_active` (opt-in, off by default), so `_dispatch_cwd`
(line 427) falls back to the shared `config.homelab_repo_path`. The machinery is
all present — `worktree_facade` exposes `branch_name`, `create_worktree`,
`remove_worktree`, `worktree_dir`, `worktree_exists`, `worktree_is_dirty`, and
ADR-0014 already does done-commit-redispatch + FF-only landing.

P2 change: **default worktree isolation ON for local coding bindings.** Invert the
gate so a local (non-remote) candidate gets a worktree unless explicitly disabled.
Remote bindings keep `{}` (they run in `binding.repo_path`; `_effective_run_cap`
already caps them at 1). `worktree_dir(repo, binding, issue_id)` is deterministic
per issue, so a resumed/warm session for the same issue lands in the same path —
no churn. With isolation on, two `run_cap` runs no longer share a checkout, so the
"any two concurrent shared-tree runs conflict" failure is gone.

### Layer 2 — Dependency ordering (unchanged): `blocked_by`

Exactly as decided above. A `todo` issue is eligible only when every id in
`blocked_by` resolves to `done`/`archived`; gated issues stay `todo`. Forces order
(B after A).

### Layer 3 — Mutual exclusion (NEW): `locks` label-set per issue

`blocked_by` forces *order*; it cannot say "A and B may run in any order but never
*at the same time*." For that, add a **`locks` JSON array of free-text labels** to
the issue (e.g. `locks: ["scheduler", "web-api"]`). Eligibility rule:

- A `todo` candidate is lock-eligible only if its lock set is **disjoint** from the
  union of lock sets held by currently-running (in-flight) issues.
- Within a single tick, once a candidate is selected its locks join a "claimed this
  tick" set; a later candidate whose locks intersect that set is skipped this tick.
- Empty `locks` ⇒ never excluded by this rule (independent work parallelizes
  freely).

Label-set (not a single mutex-group key) because two same-size representations,
and the set is correct on the edge case where work touches two areas
(`["scheduler","web-api"]` excludes both a scheduler-only and a web-api-only
peer). Locks are *advisory co-run hints authored by the operator*, not derived
from file paths — deriving them is YAGNI at this scale.

### Selection algorithm (one place: `list_candidates` consumer / `run_tick`)

Filter `todo` issues by, in order: (1) dependency-satisfied, (2) lock-disjoint from
in-flight, (3) lock-disjoint from already-claimed-this-tick. Dispatch the survivors
up to `_effective_run_cap`. No new state column, no new issue status — gated issues
stay `todo`; only *selection* is filtered.

### Schema (Alembic 0010): two columns, not one

`issue.blocked_by TEXT` (JSON int array) **and** `issue.locks TEXT` (JSON string
array). Single migration. JSON columns over join tables — single-user, dozens of
issues, mirrors the `.kanban` frontmatter shape.

### Revised slice plan (supersedes 105-109 above)

- **105** — schema: add **both** `blocked_by` and `locks` columns + Alembic 0010 +
  tracker reads both as typed lists.
- **106** — dependency dispatch gate (`blocked_by`).
- **107** — create/patch API carries `blocked_by` + `locks` (cycle reject for
  `blocked_by`). API-only; no folder mirror (see Update (3)).
- **108** — isolation: worktree-per-run default-ON for local bindings.
- **109** — mutual-exclusion lock gate (the selection filter above).
- **110** — UI read-only "waiting on #N" / "locked: scheduler" chip.
- **111** — MANUAL: backup → Alembic 0010 → `next build` → restart symphony-host +
  podium → live verify (independent issues parallelize in separate worktrees;
  `blocked_by` waits; lock-sharing issues serialize even when both eligible).
- **112** — repurpose `/podium-issues` into a plan→Podium slicer (no folder scan);
  retire the old kanban-mirror skill. See Update (3).
- **113** — merge-contention fix: FF-fail → rebase-onto-base + retry, then block.
  See Update (4). Feeds 111's deploy gate.

### Calibration risks for the MANUAL slice

- **Warm/claude_persist sessions** were historically exercised in the shared tree.
  Confirm a resumed run re-enters its deterministic worktree cleanly (same
  `worktree_dir`) and the warm session's cwd matches.
- **Worktree cleanup / disk**: many parallel runs ⇒ many worktrees; confirm
  `remove_worktree` fires on terminal outcomes and FF-landing still works.
- **The self-binding (`symphony`) dogfoods this** — the deploy itself runs through
  Symphony, so verify on a throwaway pair before trusting it broadly.

## Update 2026-06-23 (3) — authoring path: slice plans straight into Podium (one skill)

Operator asked for the authoring chain `grill-me → dev-plan → podium-issues` where
`podium-issues` slices the plan directly into Podium issues — like `to-issues`
slices a plan into `.kanban` files, but adapted for Podium — with **no separate
folder-scan step** (today's flow is two skills: `/to-issues` writes `.kanban`,
then `/podium-issues` mirrors the folder into Podium).

Decision — make `/podium-issues` a **plan slicer that writes directly to Podium**,
not a folder mirror:

1. It reuses `to-issues`' slicing logic (vertical tracer-bullet slices, explicit
   acceptance criteria, repo-correct verification command, dependency order) but
   the sink is Podium, not `.kanban` files.
2. It creates issues **in dependency order (blockers first)** via the create path,
   so it knows each blocker's real Podium id before writing a dependent's
   `blocked_by` — **no kanban-id→Podium-id translation needed.** It sets `locks`
   labels inline at the same time.
3. **No folder mirroring on the Podium path — operator-confirmed 2026-06-23.** The
   slicer writes straight to Podium; the `.kanban` folder is not involved at all.
   The pre-existing kanban→Podium mirror is **retired** as part of this work (it
   was the thing the operator explicitly did not want). The `.kanban` folder + the
   separate `/to-issues` skill remain only for the unrelated Ralph local-coding
   loop; there is no kanban→Podium bridge in this design.

Consequences for the slice plan:

- **Slice 107 is API-only.** No mirror, so no kanban-id→Podium-id translation
  anywhere. What remains is the **create/patch API carrying `blocked_by` + `locks`
  with cycle reject** — exactly what the slicer skill calls.
- **New slice 112** — repurpose `/podium-issues` into the plan-slicer skill
  (authoring-time, runs in a Claude session; no scheduler/runtime code) and retire
  the old folder-mirror skill.

Accepted tradeoff (operator-confirmed): direct-to-Podium issues live in the Podium
SQLite DB, **not in git**, so there is no version-controlled diff of "what issues
this plan produced." Accepted for frictionless authoring.

## Update 2026-06-23 (4) — merge-contention fix (FF-only fails for concurrent branches off the same base)

Tracing the worktree completion lifecycle (operator question on Issue #102) surfaced
a gap that makes P2 *not* conflict-free as drafted. On `done`, Symphony lands a
run's worktree branch with `git merge --ff-only` (`web/api/worktree.py:162`). FF-only
**cannot** land two branches that both branched off the same base: with
worktree-per-run default ON (108), A and C dispatch in parallel off `main`; A lands
and advances `main`; C's FF merge now fails because base moved → C is forced to
`blocked` and its worktree is left behind. There is no rebase/retry anywhere today.
So every independent parallel pair leaves a blocked leftover — the opposite of the
intent.

Decision (operator-approved 2026-06-23): on FF-fail, **rebase the worktree branch
onto the advanced base and retry the FF once, in-process**; a genuine rebase
conflict aborts and blocks (worktree left for inspection). Rebasing a *local* branch
onto the *local* base makes no remote contact, so the agents-don't-touch-remotes
rule is untouched. Single in-process rebase rather than an agent re-dispatch+counter:
a non-conflicting rebase is deterministic and needs no agent; re-dispatch plumbing is
the upgrade path only if real conflicts become common. Captured as **slice 113**
(lock `web-api`, the merge path), feeding the 111 deploy gate.
