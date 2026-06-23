---
name: symphony-workflow-author
description: "Author WORKFLOW.md autonomy policy for an INFRA Symphony binding. Infra-only (ADR-0011): coding bindings ignore WORKFLOW.md, so refuse them. Tracker-agnostic across Podium and dormant Plane because it edits repository policy on disk."
---

# Symphony Workflow Author

Author or replace a bound repository `WORKFLOW.md` — the per-repo **autonomy policy** for an infra binding.

## Binding-type gate (ADR-0011)

`WORKFLOW.md` is **infra-only**. Symphony does not read it for `coding` bindings — they treat the issue as the prompt and take repo conventions/safety from the repo's native agent config (`CLAUDE.md`/`AGENTS.md`), not from a Symphony-rendered file. Before authoring, resolve the binding's `type`:

- `infra` → proceed.
- `coding` → **refuse**. Do not write `WORKFLOW.md`; it would be ignored at dispatch. Tell the operator that coding-binding policy/safety belongs in the repo's `CLAUDE.md`/`AGENTS.md`.

`WORKFLOW.md` carries **autonomy** instruction (how to operate under Symphony's orchestration), not safety enforcement; safety remains the bound repo's responsibility.

## Generic template

Start every infra `WORKFLOW.md` from the bundled project-agnostic template at `templates/WORKFLOW.infra.md` (relative to this skill). It is the generalized infra autonomy policy — agent role, before-acting/git/execution/completion rules, and plan/build mode lifecycle — with **no** project specifics baked in. Adapt only binding-level autonomy knobs (front-matter `poll_interval_ms`/`run_timeout_ms`, medium-risk posture). Do **not** re-add project specifics (host/service doc layout, access sub-agent names, absolute plan paths, owner identity) — those belong in the repo's `CLAUDE.md`/`AGENTS.md`, which the template tells the agent to read. The template names the Symphony engine interface (`plane` verbs, output contract, mode lifecycle) deliberately; that is common to every binding, not project-specific.

## Tracker posture

This skill is tracker-agnostic. It does not write Podium or Plane. It edits repository policy on disk, then render-tests against `prompt_renderer.py` so either tracker can supply Issue fields.

## Workflow

1. Resolve the target repo from the binding entry.
2. Confirm the repo has a binding in `bindings.yml` or in Podium's binding table.
3. Read repo orientation files and the prompt renderer contract.
4. Interview or use supplied operator policy for sandbox boundaries, forbidden paths, mode behaviour, tests, identity, and timeouts.
5. When a binding may need incremental investigation, document that operators can select the `checkpointed-exploration` Skill to force one bounded exploration step per Run followed by Question Park review.
6. Write `WORKFLOW.md`.
7. Render-test with representative Issue fields.
8. Commit only the target repo Workflow change when running as a live authoring session.

## Safety rules

- Never read or print secret files.
- Never write a Workflow for an unbound repo.
- Never restart Symphony or file smoke Issues from this skill.
- For live external systems, require sandbox-boundary instructions before authoring.

## Verification

Run:

```bash
cd /home/james/symphony && uv run pytest tests/skills/test_workflow_author.py
```
