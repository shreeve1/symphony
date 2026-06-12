---
name: symphony-binding-scaffold
description: "Create a Podium-backed Symphony binding by inserting the binding row in Podium SQLite and appending tracker: podium to bindings.yml. Does not call Plane."
---

# Symphony Binding Scaffold

Create a new Symphony binding for the Podium era.

## Prerequisites

- Symphony repo at `/home/james/symphony`.
- Writable Podium DB path from `PODIUM_DB_PATH` or `web.api.db.resolve_db_path()`.
- Target repository exists locally and has a `WORKFLOW.md` ready to author or replace.

## Workflow

1. Resolve target binding name, repo path, base branch, default agent, and binding type.
2. Run `scaffold_podium_binding(...)` from `skill_migration.py`.
3. Verify the Podium `binding` row exists in SQLite.
4. Verify `bindings.yml` contains the same binding with `tracker: podium`.
5. Do not create any tracker-side project. Podium treats the binding itself as the project.

## Safety rules

- No Plane API calls.
- No `plane_adapter` imports.
- Do not read or print `/home/james/symphony-host.env`.
- Show the `bindings.yml` diff before committing.
- If `bindings.yml` or the DB already contains the binding name, stop instead of merging entries.

## Verification

Run:

```bash
cd /home/james/symphony && uv run pytest tests/skills/test_binding_scaffold.py
```
