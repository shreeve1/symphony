# Symphony

Symphony is the scheduler that polls a Plane project for candidate issues, dispatches each to a coding agent against a bound git repo, and posts the agent's results back to the issue. Originally built to manage the homelab infrastructure repo; being generalized to serve any repo.

## Language

**Symphony**:
The engine: poll Plane → select candidate issue → render prompt → dispatch to an agent → comment results back. One engine, many projects.
_Avoid_: "the bot", "the runner"

**Project Binding**:
The mapping that ties one Plane project to one git repo plus its dispatch config. The unit Symphony iterates over once generalized. A binding carries: the `plane_project_id` and its [[tracker-contract]] (the per-project Role→name+UUID mapping); the repo path and base branch; `default_agent` (pi or claude) with per-issue `agent:claude`/`agent:pi` label override; the approval-gate policy (opt-in, **default off** — homelab opts in); and the [[Landing]] policy (**default local**). All bindings share one workspace-scoped Plane API key for the single `homelab` workspace, differing only by `plane_project_id`.
_Avoid_: "workspace" (that is a Plane-level concept above the project)

**Mode**:
The kind of work an issue requests, resolved from its Plane labels. Current values: **plan** (produce a reviewable plan artifact, no production changes), **build** (execute an already-approved plan), **execute** (default; routine change). Mode is split across two layers: the engine owns Mode as *mechanism* — it resolves Mode from labels, exposes it to the renderer as a prompt variable, and uses it for the side-effect backstop (plan→artifact written, build→commit present) and Plane-state defaults; the [[Workflow]] owns what each Mode *means* as instruction for the repo. The fixed mode set and their side-effects live in the engine; the work each mode entails lives in `WORKFLOW.md`.
_Avoid_: "task type", "stage"

**Agent**:
The coding tool Symphony shells out to in order to do an issue's work. Today only **pi**; generalizing to also include **claude**. Each agent has its own dispatch shape: pi runs one-shot, claude runs in a tmux send-keys session.
_Avoid_: "model" (the model is a parameter of an agent, not the agent itself)

**Workflow**:
The per-repo prompt policy — a `WORKFLOW.md` at the bound repo's root that Symphony reads on each dispatch to render the prompt. It is the *whole* policy for that repo: the agent self-selects relevance from the issue's labels rather than Symphony selecting prompt fragments by label. Symphony's renderer is pure mechanism (variable substitution, issue/comment escaping, schedule block); the Workflow supplies all repo-specific instruction. A Workflow is mandatory: a binding whose repo has no readable `WORKFLOW.md` is a hard config error — Symphony refuses to dispatch, skips the issue, and posts a blocked comment naming the missing file. There is no built-in fallback policy.
_Avoid_: "domain overlay" (the homelab-era label-selected fragments; dropped in favour of one flat per-repo Workflow)

**Tracker Adapter**:
The seam that isolates all Plane-specific API calls behind one interface, so the engine talks to "a tracker" rather than to Plane directly. Borrowed from sortie's vocabulary. Keeping Plane today; the seam is what makes a future move to another tracker (e.g. GitHub Issues) a one-adapter swap instead of an engine rewrite.
_Avoid_: "Plane client" (the adapter is the abstraction; the Plane client is one implementation of it)

**Tracker Contract**:
The per-binding mapping from the **Roles** Symphony's engine cares about to a specific project's concrete tracker vocabulary (label/state names plus their per-project UUIDs). A **Role** is a thing the engine branches on — `mode:plan`, `mode:build` (execute is the absence of both), the `agent:*` dispatch override, the `approval-required` gate, `approved`, `scheduled`, and the five states (Todo / In Review / Running / Blocked / Done). The engine references Roles, never raw label strings; each [[project-binding]] supplies the names and UUIDs that satisfy them, and a Role a binding omits simply disables that behaviour. This is the concrete shape the [[tracker-adapter]] resolves. Replaces the old single global enum that lived inside the homelab repo.
_Avoid_: "the labels" (a Role is the engine-facing abstraction; labels/states are one project's concrete fillers), "domain labels" (patrol/security/infra… were prompt-routing, now [[Workflow]] content, never engine Roles)

**Agent Adapter**:
The seam that isolates each agent's dispatch shape behind a common interface — pi (one-shot subprocess) and claude (tmux send-keys session) are two implementations. The engine selects and drives an adapter without knowing the agent's mechanics.
_Avoid_: "runner" (the engine is the runner; an adapter is one agent's dispatch implementation)

**Done Marker**:
A unique per-run nonce string the agent prints when it finishes, letting Symphony detect completion of a tmux session that has no process exit code.
_Avoid_: "sentinel" (use Done Marker consistently)

**Verdict**:
The outcome of a single dispatch, declared by the agent via a `SYMPHONY_RESULT:` line whose value is one of **done** / **review** / **blocked** (mapping to the Plane states Done / In Review / Blocked). Last occurrence wins; unknown/absent falls through to a heuristic. The agent may also emit a `SYMPHONY_SUMMARY:` line for the human-readable Plane comment. For claude (tmux) the same lines are scraped from the pane before the Done Marker, backstopped by post-run side-effect inspection (commit present, plan artifact written).
_Avoid_: "ok/failed" (the real vocabulary is done/review/blocked), "exit status" (that is one input, not the verdict itself)

**Run**:
A single dispatch of one issue to one agent — the unit a Verdict describes. A Run may execute as one autonomous pass today, or later as a staged pipeline (research → … → commit) where stages hand off one at a time inside the same Run.
_Avoid_: "job" (a Run is one dispatch; the scheduler tick that may start several Runs is not itself a Run)

**Run Worktree**:
The isolated git worktree-plus-branch Symphony creates for each Run, so concurrent Runs — even against the same repo — never share a working tree. Created at dispatch, torn down after the Verdict is reconciled. This is what lets multiple agents work one repo at the same instant.
_Avoid_: "workspace" (a Plane-level concept), "checkout" (the shared repo checkout is exactly what a Run Worktree avoids touching)

**Landing**:
Converging a completed Run's branch back into the repo's base branch. Symphony's default is **local**: the Run Worktree is torn down but its branch ref is kept, committed and unpushed, to be merged by hand later (the rpiv-merge pattern). Symphony never auto-pushes or auto-merges by default; a per-binding policy can opt into push/PR or auto-merge, but the homelab/infra binding stays local.
_Avoid_: "deploy" (Landing merges a branch; what happens to infra after a merge is separate), "PR" (a PR is one optional Landing shape, not Landing itself)

**Project Scaffold**:
The skill that stands up a new Plane project to match a repo and registers it with Symphony in one pass. It creates the project in the `homelab` workspace from a standard template (states Todo / In Review / Running / Blocked / Done; labels plan / build / approval-required + agent:claude / agent:pi), introspects the fresh per-project state/label UUIDs onto the binding, appends a complete entry to `bindings.yml`, and drops a `WORKFLOW.md` stub for the human to author. Project creation is a live Plane mutation. It does *not* carry the homelab-era domain labels (patrol/security/infra/…).
_Avoid_: "template" (the template is the static shape the scaffold applies; the scaffold is the act of applying it and registering the binding)

## Relationships

- A **Project Binding** maps one Plane project to exactly one repo
- An issue carries one **Mode** (resolved from labels)
- Symphony dispatches an issue to one **Agent**, as one **Run**
- Each **Run** executes in its own **Run Worktree**; a global cap bounds how many Runs are live at once
- A finished **Run**'s branch is reconciled by **Landing** (default local/manual)

## Flagged ambiguities

- (none yet)
