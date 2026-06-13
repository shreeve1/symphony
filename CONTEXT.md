# Symphony

Symphony is the scheduler that polls a Plane project for candidate issues, dispatches each to a coding agent against a bound git repo, and posts the agent's results back to the issue. Originally built to manage the homelab infrastructure repo; being generalized to serve any repo.

## Language

**Symphony**:
The engine: poll Plane → select candidate issue → render prompt → dispatch to an agent → comment results back. One engine, many projects.
_Avoid_: "the bot", "the runner"

**Podium**:
The operator console and native tracker that replaces Plane as Symphony's human-facing surface. Symphony owns Podium's schema, lifecycle, AI-shaped metadata, and live update stream end-to-end; the [[tracker-adapter]] seam stays, with Podium as one more implementation alongside Plane. Plane is retained only as a transitional safety net during binding-by-binding migration; once both bindings cut over, Plane is archived. Podium is paired with Symphony the way a podium is paired with a conductor: the surface the operator stands at, distinct from the engine that does the conducting.
_Avoid_: "the UI" (Podium is the tracker too, not just a frontend), "Symphony Web" (reads as a sub-module rather than a thing), "the dashboard" (Podium is the primary control surface, not a debug view)

**Project Binding**:
The mapping that ties one tracker project to one git repo plus its dispatch config. The unit Symphony iterates over. A binding carries: its tracker kind (`podium` today; Plane retained only for rollback/dormant adapter compatibility), the repo path and base branch; `default_agent` (currently pi only, see [[Agent]]); a **binding_type** of `coding` or `infra` that gates several engine behaviours; an `approval.enabled` flag (off for the current homelab and trading bindings — and coding bindings skip the approval gate regardless); and the [[Landing]] policy. **Coding bindings** (today: `trading`) skip Symphony's schedule, blocked reconciler, and approval gate — the agent owns its own git operations and Symphony performs no landing step. **Infra bindings** (today: `homelab`) run all three and may project approval/schedule roles onto Podium issue columns.
_Avoid_: "workspace" (that is a Plane-era concept above the project)

**Mode**:
Historical: superseded by [[Skill]] in 2026-06-Podium. Plane-era Mode values (`plan`, `build`, `execute`, `conversation`) survive only as a compatibility bridge inside the prompt renderer and scheduler until every caller speaks Skill directly.
_Avoid_: "task type", "stage"

**Agent**:
The coding tool Symphony shells out to in order to do an issue's work. **Currently pi only.** The claude tmux-send-keys agent existed historically but was removed when Symphony went thin-engine; the [[agent-adapter]] seam remains so claude (or another agent) can be reintroduced without touching the engine. pi dispatches one-shot via `--print --no-session --provider <p> --model <m>` from the bound repo's checkout directory.
_Avoid_: "model" (the model is a parameter of an agent, not the agent itself)

**Workflow**:
The per-repo prompt policy — a `WORKFLOW.md` at the bound repo's root that Symphony reads on each dispatch to render the prompt. It is the *whole* policy for that repo: the agent self-selects relevance from the issue's labels rather than Symphony selecting prompt fragments by label. Symphony's renderer is pure mechanism (variable substitution, issue/comment escaping, schedule block); the Workflow supplies all repo-specific instruction. A Workflow is mandatory: a binding whose repo has no readable `WORKFLOW.md` is a hard config error — Symphony refuses to dispatch, skips the issue, and posts a blocked comment naming the missing file. There is no built-in fallback policy.
_Avoid_: "domain overlay" (the homelab-era label-selected fragments; dropped in favour of one flat per-repo Workflow)

**Tracker Adapter**:
The seam that isolates tracker-specific reads and writes behind one interface, so the engine talks to "a tracker" rather than to a concrete backend. Borrowed from sortie's vocabulary. Plane is retired for active bindings as of the Podium cutover: both `homelab` and `trading` use Podium, while the Plane adapter remains dormant as the ADR-0002 hedge and rollback aid. The `trading` Plane project was archived 2026-06-11 (#023d) and its rollback contract removed; the `homelab` Plane project and rollback contract are retained (archive deferred to a follow-up issue).
_Avoid_: "Plane client" (the adapter is the abstraction; the Plane client is one implementation of it)

**Tracker Contract**:
The per-binding mapping from the **Roles** Symphony's engine cares about to a specific project's concrete tracker vocabulary (label/state names plus their per-project UUIDs). A **Role** is a thing the engine branches on — `mode:plan`, `mode:build` (execute is the absence of both), the `agent:*` dispatch override, the `approval-required` gate, `approved`, `scheduled`, and the five states (Todo / In Review / Running / Blocked / Done). The engine references Roles, never raw label strings; each [[project-binding]] supplies the names and UUIDs that satisfy them, and a Role a binding omits simply disables that behaviour. This is the concrete shape the [[tracker-adapter]] resolves. Replaces the old single global enum that lived inside the homelab repo. [[Podium]] additionally carries an **Archived** issue state — a tracker-side disposal state that is deliberately *not* an engine Role: the engine never selects archived work (scheduler and reconcilers cannot reach it), and post-run it honors archived as terminal — a Run that finishes on an already-archived issue writes no verdict state transition and its [[Run Worktree]] is torn down, output discarded.
_Avoid_: "the labels" (a Role is the engine-facing abstraction; labels/states are one project's concrete fillers), "domain labels" (patrol/security/infra… were prompt-routing, now [[Workflow]] content, never engine Roles)

**Agent Adapter**:
The seam that isolates each agent's dispatch shape behind a common interface — pi (one-shot subprocess) and claude (tmux send-keys session) are two implementations. The engine selects and drives an adapter without knowing the agent's mechanics.
_Avoid_: "runner" (the engine is the runner; an adapter is one agent's dispatch implementation)

**Done Marker**:
A unique per-run file the agent creates when it finishes, letting Symphony detect completion of a tmux session that has no process exit code. (Originally a printed nonce string scraped from the pane; amended to a file-based contract — see ADR-0001 amendment.)
_Avoid_: "sentinel" (use Done Marker consistently)

**Verdict**:
The outcome of a single dispatch, declared by the agent via a `SYMPHONY_RESULT:` line whose value is one of **done** / **review** / **blocked** (mapping to the Plane states Done / In Review / Blocked). Last occurrence wins; unknown/absent falls through to a heuristic. The agent may also emit a `SYMPHONY_SUMMARY:` line for the human-readable Plane comment. For claude (tmux) the same lines are read from the per-run result file written before the Done Marker; there is no side-effect inspection backstop (parity with pi).
_Avoid_: "ok/failed" (the real vocabulary is done/review/blocked), "exit status" (that is one input, not the verdict itself)

**Run**:
A single dispatch of one issue to one agent — the unit a Verdict describes. For **coding bindings** the agent runs directly in the bound repo's checkout (no per-Run worktree) and owns its own git operations; Symphony only renders the prompt, runs the agent, scrapes the [[Verdict]], and transitions the issue. A Run may execute as one autonomous pass, or later as a staged pipeline (research → … → commit) where stages hand off one at a time inside the same Run.
_Avoid_: "job" (a Run is one dispatch; the scheduler tick that may start several Runs is not itself a Run)

**Run Worktree**:
An opt-in Podium per-Issue persistent worktree controlled by the Issue's `worktree_active` column. When active, Symphony dispatches in `worktrees/<binding>/<issue_id>` on branch `podium/<binding>/<issue_id>` and leaves the worktree intact on blocked/abort paths for operator inspection. When inactive, the agent runs directly in the bound repo checkout.
_Avoid_: "workspace" (a tracker-level concept), "checkout" (the shared repo checkout is the non-worktree execution path)

**Landing**:
Converging a completed Run's work back into the repo's base branch. For **coding bindings** Symphony performs no landing step — the agent commits (and pushes, if its Workflow allows) directly inside the bound repo's checkout, and the human inspects / merges from there. For **infra bindings** with `worktree_active=true`, Podium attempts a fast-forward merge into the Issue's base branch when the Issue moves to Done, then tears down the worktree. If the base checkout is dirty or FF-only merge fails, the Issue moves to Blocked and the worktree remains for operator inspection. Infra bindings without active worktrees run in the bound checkout and have no separate landing step.
_Avoid_: "deploy" (Landing merges a branch; what happens to infra after a merge is separate), "PR" (a PR is one optional Landing shape, not Landing itself)

**Project Scaffold**:
The skill that stands up a new Plane project to match a repo and registers it with Symphony in one pass. It creates the project in the `homelab` workspace from a standard template (states Todo / In Review / Running / Blocked / Done; labels plan / build / approval-required + agent:claude / agent:pi), introspects the fresh per-project state/label UUIDs onto the binding, appends a complete entry to `bindings.yml`, and drops a `WORKFLOW.md` stub for the human to author. Project creation is a live Plane mutation. It does *not* carry the homelab-era domain labels (patrol/security/infra/…).
_Avoid_: "template" (the template is the static shape the scaffold applies; the scaffold is the act of applying it and registering the binding)

**Skill**:
A named, reusable agent procedure the operator can direct an issue toward (e.g. `dev-plan`, `diagnose`, `code-review`). [[Podium]] tracks Skills in three forms: an operator-curated **catalog** of known Skills (populates the UI dropdown), an Issue-level **preferred Skill** the operator names to direct the next dispatch, and a Run-level **invoked Skill** captured from the agent's output as a record of what actually ran. The catalog is non-live — refreshed by an operator command, not auto-discovered each session — and `run.skill_invoked` is advisory free-text, not foreign-keyed to the catalog (an agent may run ad-hoc Skills the catalog has not indexed).

The **preferred Skill is consume-on-dispatch**, not standing config: it is invoked exactly once. The scheduler captures it into the Run's invoked Skill, then clears the Issue's preferred Skill in the same dispatch (only once the Run row is recorded — a blocked or deferred dispatch leaves it intact). A skill-less dispatch is valid and runs as a plain agent continuation (no skill-invoke directive injected). This mirrors a CLI `/skill` invocation: the operator names a Skill once, the next Run uses it, and re-dispatches (e.g. an Operator Reply) run skill-less unless the operator names a Skill again. This is deliberately asymmetric with the other Issue-level dispatch properties (**preferred model**, **reasoning effort**), which are *standing* — they persist across every Run like a CLI session's model choice and are not consumed.
_Avoid_: "command" (a Skill is the named procedure, not its invocation syntax), "tool" (a tool is what a Skill internally calls; the two are not interchangeable)

**Playbook**:
An operator-defined multi-step procedure the operator triggers against an issue (or binding) to run a sequence of actions — the canonical examples are the rralph / tralph pipelines, but Playbooks are not limited to those. The intended primary value of [[Podium]] is letting the operator define and trigger Playbooks once an issue is "on the same page" with the AI. **Distinct from [[Workflow]]**: a Workflow is *static, per-repo, engine-read* on every dispatch (`WORKFLOW.md`); a Playbook is *operator-authored, multi-step, operator-triggered*, lives in [[Podium]], and orchestrates sequences of dispatches (and potentially other actions) rather than instructing a single one. Schema and trigger semantics are deliberately deferred pending the Playbook design pass.
_Avoid_: "Workflow" (the term collision is exactly why Playbook exists as a separate noun; never use Workflow to mean Playbook or vice versa), "pipeline" (overloaded across CI, data-eng, and agent-orchestration; Playbook is the operator-facing term)

**Issue Comments**:
The bidirectional human/AI communication thread on a [[Podium]] issue, persisted as a markdown blob per issue. The operator writes instructions, feedback, and observations and may freely edit, delete, or restructure the blob at any time. The AI agent appends a concise summary after each [[Run]] for the operator to review; AI writes are append-only. Both parties read it. The agent reads the full Comments blob into the dispatch prompt alongside `description` and [[Issue Context]]. Distinct from [[Issue Context]] (the AI's own session log, AI-managed) and from `description` (the static problem statement filed at issue creation).
_Avoid_: "chat" (Comments are async and operator-curated, not real-time chat), "thread" (overloaded with tmux sessions; "Comments" is the canonical noun)

**Issue Context**:
The AI agent's own session log per [[Podium]] issue — a persistent markdown blob the agent reads at the start of every [[Run]] and writes the full detailed Run output to at completion. Provides cross-Run continuity: every dispatch sees the agent's cumulative prior findings, replacing the comment-block prompt-injection mechanism Symphony used in the Plane era. The operator can view it in the UI but does not normally write to it; the agent owns this surface. When Issue Context exceeds a per-binding token threshold, Symphony performs an engine-built compaction step *before* dispatching the operator's next Run — it invokes the configured agent with a Symphony-owned compaction prompt template that rewrites older entries into a single summary block while preserving the most recent N Runs verbatim, then writes the trimmed result back. Compaction is housekeeping internal to the engine: it does not produce a Run row, does not appear in [[Skill]] catalog, and is invisible in the UI except for a marker line inserted into Context noting the trim. Distinct from [[Issue Comments]] (the bidirectional thread with the operator) and from the per-[[Run]] log captured to disk (the raw stdout/stderr of one dispatch).
_Avoid_: "session memory" (Issue Context is the *persisted* form across Runs; the agent's in-prompt context window of one Run is ephemeral and not the same thing), "transcript" (Issue Context is curated by the agent, not a verbatim capture)

## Relationships

- A **Project Binding** maps one tracker project to exactly one repo
- A Podium issue carries a preferred **Skill**; Mode remains a compatibility bridge
- Symphony dispatches an issue to one **Agent**, as one **Run**
- A **Run** executes either in the bound checkout or in an opt-in **Run Worktree**; a global cap bounds how many Runs are live at once
- A finished **Run** may trigger **Landing** when an infra issue uses an active Podium worktree

## Historical

- **[[Workflow]] label self-routing during [[Podium]] migration.** Resolved by Podium: `preferred_skill`, description, Comments, and Issue Context replace Plane label-selected prompt routing for active bindings.
- **[[Mode]] scheduled for removal in the Podium migration.** Resolved by Podium: Skill carries operator work shape; Mode remains only as a compatibility projection.
