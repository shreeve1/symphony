---
name: symphony-onboard-project
description: "Orchestrate Podium-era onboarding: symphony-binding-scaffold → (infra only) symphony-workflow-author → symphony-restart → symphony-binding-smoke. Preserves each sub-skill safety gate."
---

# Symphony Onboard Project

Coordinate one new Podium-backed binding from local repo to smoke-tested dispatch.

## Workflow

1. Run `symphony-binding-scaffold` to create the Podium binding row and append `tracker: podium` to `bindings.yml`.
2. **Branch on `binding_type` (ADR-0011):**
   - **`infra`**: run `symphony-workflow-author` to create or replace the repository `WORKFLOW.md` (mandatory autonomy policy for infra bindings).
   - **`coding`**: skip `symphony-workflow-author` — coding bindings ignore `WORKFLOW.md`. Instead, *flag* (warn, do not block) if the repo has no `CLAUDE.md`/`AGENTS.md`: safety and repo conventions are the repo's responsibility, not Symphony's.
3. Run `symphony-restart` after code/config changes need the live scheduler to reload.
4. Run `symphony-binding-smoke` to create a Podium smoke Issue and poll the resulting Run.

## Safety rules

- This skill owns no direct mutations; sub-skills own their specific write paths.
- Do not call `symphony-project-scaffold` for Podium onboarding.
- Do not call `symphony-plane-recover` except during legacy Plane retirement.
- Preserve service-affecting gates from `symphony-restart` unless the enclosing unattended Ralph runner has explicitly pre-approved them.
- Stop on the first failed sub-skill; do not auto-rollback.

## Verification

Run:

```bash
cd /home/james/symphony && uv run pytest tests/skills/test_onboard_project.py
```
