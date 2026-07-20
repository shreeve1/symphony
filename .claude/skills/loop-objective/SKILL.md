---
name: loop-objective
description: >
  Turn a rough intent into a well-formed loop prompt — the Markdown block
  the operator pastes into a Podium Issue body to start a new Symphony
  automation. Mirrors goal-objective's drafting shape: ask only when intent
  is genuinely ambiguous, draft a contract block, hand off to a Podium
  Issue (the operator pastes the prompt and POSTs /api/issues). Draft only
  — never write to Podium. Use when the operator says "draft a loop
  prompt", "start a new automation in symphony", "write me a loop", or
  invokes /loop-objective. Companion front-end to Podium Issue creation.
---

# loop-objective — draft a loop prompt from intent

Help the operator shape a vague automation intent into a concrete prompt
the agent can run as a loop. The skill does the *thinking* about what the
loop should be; the operator pastes the prompt into a Podium Issue body
and Symphony's dispatcher carries it forward.

Do not create Podium state yourself. Do not POST `/api/issues`, do not
touch the issue table, do not invoke `create_podium_smoke_issue` (that's
`symphony-binding-smoke`'s job, and it's not what the operator asked for
here). Your output is a drafted prompt block the operator approves, then
the operator pastes it into a Podium Issue themselves.

---

## When to use this vs creating the issue directly

- Use **loop-objective** when the operator has an intent but not a crisp
  prompt yet ("automate the weekly code-review backlog", "set up a patrol
  that watches for failed syncs", "draft me a loop that migrates the
  legacy config"). This skill infers and drafts.
- Use **direct Issue creation** when the operator already has the prompt
  body and dispatch metadata in hand.

If invoked and the intent is already crisp (every draft field supplied),
skip straight to §4 handoff.

---

## Procedure

### 1. Understand the intent

Read the operator's request and the current Symphony context. Infer:
- What the agent should *establish* (the loop's destination, not the
  activity list). A loop is a recurring or self-replenishing pattern; if
  the operator's intent is a one-shot task, say so and stop (see §5).
- When the loop is *done* (a stopping signal — usually machine-checkable).
- What re-triggers an iteration (recurrence rule, dependency-unblock, no
  re-loop at all = one-shot, or a Patrol cadence).
- Which existing Symphony binding drives the work (the issue has to live
  on a binding; check `bindings.yml` for candidates).
- Any dispatch knobs the operator named (skill, model, agent, priority,
  schedule, worktree).

Do lightweight investigation if it sharpens the draft (e.g. peek at
`bindings.yml` for an obvious binding, check whether a relevant skill is
catalogued). Delegate broad exploration to a subagent rather than reading
widely inline. Keep it cheap — this is drafting, not the work itself.

### 2. Ask only what you can't infer

Ask **at most two** clarifying questions, and only when the answer
materially changes the prompt. Ask in plain chat text. Prefer proposing a
default and letting the operator correct it over asking open-ended.

Good reasons to ask:
- The intent could mean two genuinely different loops (e.g. "automate the
  weekly review" — once-per-week patrol, or every-issue review trigger?
  Different re-loop rule).
- The operator hasn't named a target binding and more than one binding is
  a plausible home.
- The intent is one-shot work the operator miscalled a loop — flag that
  explicitly so the operator can pick: "Just file this as an Issue" vs.
  "Yes, I want a recurring pattern."

Bad reasons to ask (infer or propose a default):
- Priority (default `med`).
- Reasoning effort (default `high`, per the Podium dispatch contract).
- Dispatch metadata knobs the operator didn't name (omit them — the
  operator can set them at issue creation).
- Whether to use a worktree (default-on for coding bindings per ADR-0021;
  omit the knob if the operator didn't ask).

If intent is already clear, ask nothing.

### 3. Draft the prompt

Produce a candidate prompt block inline for the operator to react to.
Mirror the fields `goal-objective` drafts (see
`~/.claude/skills/goal-objective/SKILL.md`) so the operator gets a
familiar shape:

```
Loop prompt — <short slug>

## Loop objective
<One concrete sentence: the end state the agent should establish or the
recurring pattern it should run.>

## Stopping condition
<The verifiable signal that proves the loop is done — e.g. "all TODOs in
<repo> resolved and tagged", "patrol log shows N consecutive passes", "no
issues in <queue> for N days". Be specific.>

## Re-loop rule
<What triggers another iteration. Pick one:>
  - one-shot: run once, exit on the stopping condition.
  - on dependency: re-loop when a named Podium issue / external signal
    unblocks.
  - patrol cadence: re-loop on the binding's schedule (homelab-style
    `scheduled:` window per ADR-0018 / CONTEXT.md).
  - operator-driven: re-loop only when the operator replies with a fresh
    instruction.

## Validation per iteration
<What the agent runs to prove an iteration succeeded. Prefer a runnable
command or a checkable artifact. The agent's normal `SYMPHONY_RESULT`
contract still applies — this is the per-iteration bar the operator wants.>

## Inputs to read first
- <paths, docs, existing issues, or skills to read before acting>
- <list 2-5 things; if more, group them>

## Out of scope
- <what the agent must NOT change>
- <secrets, branches, sweep automation of existing issues, etc.>

## Iteration strategy
<How the loop is broken into iterations. Each iteration is one Run. A
handful of named steps the agent can take, with the signal that proves
each step succeeded. Example:>
- **L1: Survey** — list every place <pattern> appears; write to
  <scratch file>. Verified by: file exists, line count > 0.
- **L2: Apply** — run the migration against the first module; commit.
  Verified by: tests in <path> pass.
- **L3: Re-loop decision** — if the migration is incomplete, file a
  follow-up Issue (don't auto-continue); else exit with stopping
  condition met.

## Notes / Constraints
<Anything the agent must remember across iterations: rollback plan,
parity with existing <system>, preferred_skill/model/agent if the
operator named them, schedule windows for patrol cadence, etc.>
```

Hold the draft to the same bar `goal-objective` enforces, so the
operator's bar for `loop-objective` is consistent:
- Loop objective is one concrete end state, not a list of activities.
- Stopping condition is machine-verifiable, not a judgment call.
- Re-loop rule is one of the four explicit forms, not invented.
- Validation per iteration is runnable; if it isn't, flag it.
- Scan for load-bearing vague words ("clean", "better", "robust", "fix",
  "improve") and replace them with something measurable before
  presenting.

If you genuinely cannot fill a field from inference, say so plainly and
present the best guess you can — don't paper over it.

### 4. Confirm and hand off

Show the draft. Ask the operator to approve or edit. Once approved, hand
off:

> Paste this block into the Issue body on binding `<binding-name>` and
> set the dispatch knobs you want. Symphony's dispatcher will pick it up
> on the next tick.

The operator pastes the prompt into a Podium Issue body. They may also
set dispatch knobs at issue creation:
- `priority` (`low | med | high | urgent`)
- `preferred_skill` / `preferred_model` / `preferred_agent` (from the
  Podium model catalog and skill catalog)
- `worktree_active` (default-on for coding bindings per ADR-0021; remote
  bindings force false)
- `reasoning_effort` (default `high` per the dispatch contract)
- `schedule` / `scheduled_for` (if the re-loop rule is a patrol cadence)

The skill does not post the issue. The operator hits the create button.

---

## Output discipline

- Lead with the draft, not preamble.
- One or two questions maximum, and only when necessary.
- Never post to `/api/issues` — that's the operator's call once they
  paste the prompt.
- Never invoke `symphony-binding-smoke` — smoke issues are a binding-
  level concern, not a loop-prompt concern.
- If the operator's intent doesn't warrant a loop (one-off task,
  exploratory back-and-forth, no recurring shape), say so and suggest
  filing a single Issue directly without a draft.
