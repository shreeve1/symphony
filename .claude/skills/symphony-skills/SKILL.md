---
name: symphony-skills
description: Refresh the Podium Skill catalog from repo-local .claude/skills/SKILL.md files using python -m web.cli.podium skills refresh. Dry-run first, then live refresh after operator confirmation.
---

# Symphony Skills Catalog Refresh

Refresh the Podium `skill` table that feeds the new-Issue Skill dropdown.

## Prerequisites

- Run from `/home/james/symphony`.
- Podium database path resolves through `PODIUM_DB_PATH` or `web.api.db.resolve_db_path()`.
- Repo-local skill docs live under `.claude/skills/`.

## Workflow

1. Preview the catalog scan:

   ```bash
   cd /home/james/symphony && uv run python -m web.cli.podium skills refresh --dry-run
   ```

2. Read the dry-run output. Lines are catalog changes:
   - `+ name` means new Skill row.
   - `~ name` means changed description or source path.
   - `- name` means stale seed row removed.

3. Show the diff to the operator and get confirmation before the live write.
4. Run the live refresh:

   ```bash
   cd /home/james/symphony && uv run python -m web.cli.podium skills refresh
   ```

5. Report the resulting catalog by either rerunning the dry-run to confirm no pending changes or reading `GET /api/skills`.

## Safety rules

- No service restart, start, stop, enable, or unit edit.
- No Plane API calls.
- No `.env` or `/home/james/symphony-host.env` reads.
- No secret printing.
- Only the Podium `skill` catalog is changed.

## Verification

Run:

```bash
cd /home/james/symphony && uv run pytest tests/skills/test_catalog_maintenance_skills.py
```
