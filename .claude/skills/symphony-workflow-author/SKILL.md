---
name: symphony-workflow-author
description: "Author WORKFLOW.md for a Symphony binding. Tracker-agnostic: works for both Podium and dormant Plane bindings because it edits repository policy on disk."
---

# Symphony Workflow Author

Author or replace a bound repository `WORKFLOW.md`.

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
