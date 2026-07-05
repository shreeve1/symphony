---
name: symphony-skills
description: Refresh the Podium Skill catalog per host/per binding from each binding's host global ~/.claude/skills plus its repo .claude/skills using python -m web.cli.podium skills refresh. Dry-run first, then live refresh after operator confirmation.
---

# Symphony Skills Catalog Refresh

Refresh the Podium `skill` table that feeds the new-Issue Skill dropdown. This
normally runs automatically at `symphony-host` startup (ADR-0033); the CLI is the
manual/fallback path for refreshing without a scheduler restart.

## Prerequisites

- Run from `/home/james/symphony`.
- Podium database path resolves through `PODIUM_DB_PATH` or `web.api.db.resolve_db_path()`.
- Skills are scanned per binding (ADR-0033): each binding's host-global
  `~/.claude/skills` (scanned once per host; `binding_name` NULL) plus that
  binding's repo `.claude/skills` (scoped to the binding). Remote bindings are
  scanned over SSH; an unreachable host is skipped best-effort (its rows are left
  intact) and logged, never failing the run.

## Workflow

1. Preview the target catalog (no DB write):

   ```bash
   cd /home/james/symphony && uv run python -m web.cli.podium skills refresh --dry-run
   ```

   Output is one `[host/binding]⇥name⇥description⇥source` line per scanned skill
   (`[host/global]` for host-global rows). This lists what the catalog *would*
   contain — it does **not** diff against the existing table.

2. To preview the actual change set, diff the dry-run output against the current
   `skill` table (query the DB or `GET /api/skills`).

3. Show the diff to the operator and get confirmation before the live write.
4. Run the live refresh — it applies the changes and prints one
   `+ [host/binding] name` / `- [host/binding] name` line per scoped change as it
   writes (a scope is replaced only if its host was reachable; manual `source=''`
   rows are kept):

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
