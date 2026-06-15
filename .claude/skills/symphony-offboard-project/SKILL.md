---
name: symphony-offboard-project
description: "Orchestrate Podium-era binding teardown: symphony-bindings-status → symphony-binding-remove → symphony-restart. Inverse of symphony-onboard-project. Archive by default; purge is gated. Preserves each sub-skill safety gate."
---

# Symphony Offboard Project

Coordinate the removal of one Podium-backed binding from live status check to a reloaded scheduler. Inverse of `symphony-onboard-project`.

## Workflow

1. Run `symphony-bindings-status` to confirm the binding exists and capture situational awareness (open Issue counts, latest Run state) before any destructive step.
2. Run `symphony-binding-remove`:
   - **archive** (default, `purge=False`) — reversible: drops the `bindings.yml` entry and sets `binding.archived = TRUE`, preserving Issue/Run history.
   - **purge** (`purge=True`) — destructive: also deletes the binding's Runs, Issues, and `binding_settings`/`binding` rows. Only after the operator confirms the Issue/Run counts from step 1 are disposable.
3. Run `symphony-restart` so the live scheduler reloads `bindings.yml` and stops dispatching the removed binding. Until this runs, the removed binding stays live in the running process.

## Safety rules

- This skill owns no direct mutations; sub-skills own their specific write paths (`symphony-binding-remove` owns the `bindings.yml`/Podium DB teardown).
- Default to archive. Only `purge` when the operator has confirmed the binding's Issue/Run history is disposable.
- Do not call `symphony-plane-recover` — that is legacy Plane retirement, not Podium binding teardown.
- Preserve the service-affecting gate from `symphony-restart` unless the enclosing unattended Ralph runner has explicitly pre-approved it.
- Stop on the first failed sub-skill; do not auto-rollback.

## Verification

```bash
cd /home/james/symphony && uv run pytest tests/skills/test_offboard_project.py
```
