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

1. Preview the target catalog (no DB write):

   ```bash
   cd /home/james/symphony && uv run python -m web.cli.podium skills refresh --dry-run
   ```

   Output is one `name⇥description⇥source` line per scanned skill. This lists what
   the catalog *would* contain — it does **not** diff against the existing table.

2. To preview the actual change set, diff the dry-run output against the current
   `skill` table (query the DB or `GET /api/skills`). Compute `+`/`~`/`-` yourself:
   - `+ name` — scanned but not in DB (new Skill row).
   - `~ name` — in both but description or source differs.
   - `- name` — in DB but not scanned (stale seed row; manual rows are kept).

3. Show the diff to the operator and get confirmation before the live write.
4. Run the live refresh — it applies the changes and prints the `+ name` / `~ name` /
   `- name` diff lines as it writes:

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
