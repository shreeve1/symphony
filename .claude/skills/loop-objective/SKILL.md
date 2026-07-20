---
name: loop-objective
description: >
  Turn a rough intent into a well-formed Symphony binding draft plus a first
  Issue spec, then hand off to symphony-binding-scaffold and
  symphony-onboard-project. The binding is Symphony's polling loop (one
  binding = one automation), so the "loop contract" here is the YAML the
  scaffold will write to bindings.yml. Draft only — never write to the
  Podium DB or bindings.yml yourself. Use when the operator says "start a
  new automation in symphony", "add a new binding", "draft a loop", or
  invokes /loop-objective. Companion front-end to symphony-binding-scaffold.
---

# loop-objective — draft a Symphony binding from intent

Help the operator shape a vague automation intent into a concrete binding
contract, then hand off to the existing scaffold/onboard chain. This skill
does the *thinking* about what the loop should be; `symphony-binding-scaffold`
does the state writes and `symphony-onboard-project` orchestrates the rest.

Do not create binding state yourself. Do not write to `bindings.yml`, do not
insert Podium DB rows, do not call `scaffold_podium_binding`. Your output is a
drafted binding contract the operator approves, then you invoke
`symphony-binding-scaffold` (which itself hands off to `symphony-onboard-project`).

---

## When to use this vs `symphony-binding-scaffold` directly

- Use **loop-objective** when the operator has an intent but not a crisp
  binding spec yet ("automate the dotfiles repo", "run a Claude loop over
  my itainfra checkout", "set up a remote automation on the mac"). This
  skill infers and drafts.
- Use **symphony-binding-scaffold** directly when the operator already
  knows the exact `name` / `type` / `repo_path` / agent / remote block.

If invoked and the intent is already crisp (every draft field supplied),
skip straight to §4 handoff.

---

## Procedure

### 1. Understand the intent

Read the operator's request and the current Symphony context. Infer:
- What automation they actually want (the loop's destination, not the
  activity list).
- The repo + base branch that will be driven.
- Whether it's local or remote (SSH onto another host).
- Coding (agent owns git) vs. infra (Symphony owns Landing / scheduling /
  blocked-reconciler) — see `CONTEXT.md` "Project Binding" + ADR-0032.
- Preferred default agent + dispatch mode (default `pi` + `pi_mode: rpc`
  per ADR-0010).

Do lightweight investigation if it sharpens the draft (e.g. `ls /home/james`
for repo candidates, check `bindings.yml` for name collisions, confirm
`uv run python -c "import skill_migration"` is importable). Delegate broad
exploration to a subagent rather than reading widely inline. Keep it cheap —
this is drafting, not the work itself.

### 2. Ask only what you can't infer

Ask **at most two** clarifying questions, and only when the answer
materially changes the contract. Ask in plain chat text. Prefer proposing a
default and letting the operator correct it over asking open-ended.

Good reasons to ask:
- The intent could mean two genuinely different loops (e.g. "automate my
  dotfiles" — is this the user's dotfiles or the n8n remote's dotfiles?
  Different `repo_path` + `remote:` block).
- The operator is choosing between `coding` and `infra` without obvious
  signal (a tied trade-off; the engine surface changes).

Bad reasons to ask (infer or propose a default):
- `name` slug (propose one; validate non-empty + no whitespace against
  `_validate_binding_name` at `skill_migration.py:535` — stricter checks
  reopen handoff for a rename).
- `default_agent` (default `pi`).
- `binding_type` (default `coding`; `infra` only when the operator says
  "homelab-style" / "patrol" / "schedule windows").
- `pi_mode` (default `rpc` for `pi` bindings; only ask if the operator
  mentions rolling back to one-shot).

If intent is already clear, ask nothing.

### 3. Draft the contract

Produce a candidate contract inline for the operator to react to. Mirror
the fields `symphony-binding-scaffold` expects (`PodiumBindingScaffoldRequest`
in `skill_migration.py:34+`):

```
Loop draft — <proposed-binding-name>

name:                  <slug — non-empty, no whitespace>
type:                  <coding | infra>
repo_path:             <absolute path>
base_branch:           <main | other>
default_agent:         <pi | claude>
pi_mode:               <rpc | one-shot>            # pi bindings only
# Optional — set both to make this a remote binding (ADR-0012). Requires
# coding + pi + rpc. host_alias is display-only sidebar grouping (ADR-0039).
# remote_host:         <host or IP>
# remote_user:         <ssh user>
# remote_identity:     <ssh key path, optional>
# remote_host_alias:   <display label, optional — auto-derived+backfilled
#                        for a shared host>

First issue (smoke):
  description:         <one concrete sentence — the work you want dispatched>
  priority:            <low | med | high | urgent>
  preferred_skill:     <skill slug the agent should consume, optional>
  preferred_model:     <provider/model id, optional>
  preferred_agent:     <pi | claude, optional — defaults to binding's>
  reasoning_effort:    <none | minimal | low | medium | high | xhigh>
  worktree_active:     <true | false>             # ADR-0021 default-on for
                                                  coding; remote forces false

Out of scope:          <what must NOT change — secrets, sweep automation of
                        existing Issues, schedule changes, etc.>
Notes / Constraints:   <rollback, parity (remote ⇒ coding+pi+rpc), ADR-0011
                        "skip WORKFLOW.md for coding", ATR-0016 "project
                        preamble replaces WORKFLOW.md on infra", etc.>
```

Hold the draft to the same bar `symphony-binding-scaffold` enforces, so the
handoff is clean:
- `name` is non-empty with no whitespace.
- `repo_path` exists on disk; `base_branch` exists in that repo.
- `type` is `coding` unless the operator named infra-triggers (patrol,
  scheduling, blocked-reconciler, approval gates).
- `pi_mode` is `rpc` unless the operator is explicitly rolling back to
  one-shot.
- Remote block requires `coding` + `pi` + `rpc` (enforced by
  `symphony-binding-scaffold`).
- For coding bindings, do NOT propose authoring a `WORKFLOW.md` (ADR-0011) —
  flag a missing `CLAUDE.md`/`AGENTS.md` in the target repo as a *safety
  hint*, not a scaffold step.
- For infra bindings, the chain will run `symphony-workflow-author` after
  scaffold — note that in `Notes / Constraints`.

If you genuinely cannot fill a field from inference, say so plainly and
present the best guess you can — don't paper over it.

### 4. Confirm and hand off

Show the draft. Ask the operator to approve or edit. Once approved, hand off:

> Ready. Invoking the `symphony-binding-scaffold` skill to write the row and
> append the YAML entry.

Then invoke **symphony-binding-scaffold**. The scaffold still handles, on
its own:
- its duplicate-name guard (raises if `name` exists in Podium DB or
  `bindings.yml`);
- the remote-binding invariants (coding + pi + rpc);
- the Schema creation idempotency.

After scaffold returns OK, do not chain further. The operator decides
whether to run `symphony-onboard-project` (which adds `symphony-restart` and
`symphony-binding-smoke`) — those prompts come from the chain, not from a
gap in the draft. Don't pre-answer them here.

---

## Output discipline

- Lead with the draft, not preamble.
- One or two questions maximum, and only when necessary.
- Never write binding state — that's `symphony-binding-scaffold`'s job.
- Never restart Symphony — that's `symphony-restart`'s job.
- If the operator's intent doesn't warrant a new loop (one-off task on an
  existing binding, exploratory prompt tuning, no durable automation
  shape), say so and suggest filing a Podium Issue directly on an existing
  binding instead of drafting a new binding.
