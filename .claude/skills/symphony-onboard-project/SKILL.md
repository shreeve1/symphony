---
name: symphony-onboard-project
description: "Orchestrate Podium-era onboarding: symphony-binding-scaffold → (infra only) symphony-workflow-author → symphony-restart → symphony-binding-smoke. Preserves each sub-skill safety gate."
---

# Symphony Onboard Project

Coordinate one new Podium-backed binding from local repo to smoke-tested dispatch.

## Workflow

1. Run `symphony-binding-scaffold` to create the Podium binding row and append `tracker: podium` to `bindings.yml`.
   - **Adding another folder on an existing remote host** (multiple projects under one host): this is supported and needs no data-model change. Give the new binding a **distinct `name`** (binding `name` is the only uniqueness constraint — reusing it is the sole hard blocker, so do not treat a matching host as a collision) and reuse the same `remote_host`/`remote_user`. The scaffold auto-detects the shared host and backfills a display-only `remote_host_alias` onto every binding on it so they group under **one** sidebar header (ADR-0039). Example: `n8n` → `/home/itadmin/itastack` and `n8n-dotfiles` → `/home/itadmin/dotfiles` both group under `N8N`.
2. **Branch on `binding_type` (ADR-0011):**
   - **`infra`**: run `symphony-workflow-author` to create or replace the repository `WORKFLOW.md` (mandatory autonomy policy for infra bindings).
   - **`coding`**: skip `symphony-workflow-author` — coding bindings ignore `WORKFLOW.md`. Instead, *flag* (warn, do not block) if the repo has no `CLAUDE.md`/`AGENTS.md`: safety and repo conventions are the repo's responsibility, not Symphony's.
3. Run `symphony-restart` after code/config changes need the live scheduler to reload. **Expect `bindings.yml` to show as modified in restart's pre-sanity** — step 1 (`symphony-binding-scaffold`) just appended to it. Treat that one path as expected chain state, not a "risky unrelated change." Genuinely unrelated edits (e.g. `scheduler.py`, `config.py`, `web/api/*`) still warrant the stop-and-ask gate. **Note:** this restart reflects the current disk head — if pre-sanity reports the running `code_sha` as `stale`, the restart advances the scheduler to head and lands every commit since the last boot, not just the new binding. Usually fine, but know what you're landing.
4. Run `symphony-binding-smoke` to create a Podium smoke Issue and poll the resulting Run. For `coding` bindings this skips the `WORKFLOW.md` check; for all bindings it auto-dispatches a **real** agent run against the target repo. Live API auth comes from the forbidden env file — use the in-process TestClient pattern documented in `symphony-binding-smoke` unless James provides a live session.

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
