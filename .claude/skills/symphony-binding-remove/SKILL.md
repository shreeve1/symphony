---
name: symphony-binding-remove
description: "Remove a Podium-backed Symphony binding by dropping its bindings.yml entry and archiving (default, reversible) or purging (destructive) its Podium SQLite row. Inverse of symphony-binding-scaffold. Does not call Plane."
---

# Symphony Binding Remove

Remove an existing Symphony binding for the Podium era. Inverse of `symphony-binding-scaffold`.

Two modes, both drop the `bindings.yml` entry so the dispatch loop stops picking the binding up:

- **archive** (default, `purge=False`) — reversible. Sets `archived = TRUE` on the `binding` row, preserving its Issue/Run history.
- **purge** (`purge=True`) — destructive. Deletes the binding's Runs, Issues, `binding_settings`, and `binding` row. Use only when history is not worth keeping.

## Prerequisites

- Symphony repo at `/home/james/symphony`. Run everything from this directory (`skill_migration` is a repo-root module).
- Writable Podium DB path. With no `PODIUM_DB_PATH` set and `/var/lib/symphony` absent, `web.api.db.resolve_db_path()` resolves to the live `/home/james/symphony/podium.db`.

## Workflow

1. Resolve inputs:
   - `name` — the binding name to remove; non-empty, no whitespace.
   - `purge` — `False` (archive, default) or `True` (destructive delete).
2. **Pre-flight check (always run first).** Confirm what you are about to remove and, for `purge`, how much history it destroys:

   ```bash
   cd /home/james/symphony && uv run python - <<'PY'
   import sqlite3
   from web.api.db import resolve_db_path
   con = sqlite3.connect(resolve_db_path())
   name = "NAME"
   print("binding:", con.execute(
       "SELECT name, display_name, archived FROM binding WHERE name = ?", (name,)
   ).fetchone())
   issues = con.execute(
       "SELECT COUNT(*) FROM issue WHERE binding_name = ?", (name,)
   ).fetchone()[0]
   runs = con.execute(
       "SELECT COUNT(*) FROM run WHERE issue_id IN (SELECT id FROM issue WHERE binding_name = ?)",
       (name,),
   ).fetchone()[0]
   print(f"issues={issues} runs={runs}")
   PY
   grep -nA10 "name: NAME" bindings.yml
   ```

3. **Destructive-purge gate.** For `purge=True`, show the operator the Issue/Run counts from step 2 and get explicit confirmation before running. Archive (the default) is reversible and needs no extra gate beyond the normal diff review.
4. Run `remove_podium_binding(...)`. It takes the binding `name` plus required keyword-only `db_path`, `bindings_path`, and optional `purge`:

   ```bash
   cd /home/james/symphony && uv run python - <<'PY'
   from pathlib import Path
   from web.api.db import resolve_db_path
   from skill_migration import remove_podium_binding

   result = remove_podium_binding(
       "NAME",
       db_path=resolve_db_path(),
       bindings_path=Path("/home/james/symphony/bindings.yml"),
       purge=False,   # False = archive (reversible); True = delete history
   )
   print(result)
   PY
   ```

   The call raises `ValueError` if `name` is absent from both `bindings.yml` and the Podium DB. If the entry exists in only one place, it removes what it finds and reports the rest as `absent` / `removed_from_bindings_yml=False` rather than failing.
5. The removed binding stays live in memory until `symphony-host.service` reloads `bindings.yml`. Restart via the `symphony-restart` skill (ask James) when ready.

## Result shape

`PodiumBindingRemovalResult`:

- `binding_name` — the name removed.
- `removed_from_bindings_yml` — `True` if a `bindings.yml` entry was dropped.
- `db_action` — `"archived"`, `"deleted"`, or `"absent"`.
- `deleted_issue_count` / `deleted_run_count` — non-zero only for `purge`.

## Safety rules

- No Plane API calls.
- No `plane_adapter` imports.
- Do not read or print `/home/james/symphony-host.env`.
- Show the `bindings.yml` diff before committing. `_remove_binding` round-trips the file through `yaml.safe_load` → `yaml.safe_dump`, so any comments in `bindings.yml` are stripped (same side effect as `symphony-binding-scaffold`, C-0171). The diff is the only guard against silent comment loss; restore wanted comments from git if needed.
- Default to archive. Only `purge` when the operator has confirmed the Issue/Run history is disposable.
- `bindings.yml` mutation here is the deliberate inverse of `symphony-binding-scaffold`; no other skill should remove binding entries.
- **Self-binding caveat.** Removing the `symphony` binding tears down Symphony's binding to its own repo (`/home/james/symphony`) — the highest-risk of the live bindings. Do not remove `symphony` (or any binding the operator did not name) without explicit confirmation; after a restart the scheduler will no longer dispatch Issues filed against it.

## Reversing an archive

Archive is reversible but not a single command: re-add the binding's entry to `bindings.yml` (the scaffold/remove pair owns that file) and clear the flag with `UPDATE binding SET archived = FALSE WHERE name = 'NAME'`, then `symphony-restart`. Purge is not reversible — Issue/Run history is gone (recover only from a `podium.db` backup).

## Verification

Confirm the binding is gone from `bindings.yml` and check the DB state (replace `NAME`):

```bash
cd /home/james/symphony
grep -n "name: NAME" bindings.yml || echo "absent from bindings.yml (expected)"
uv run python - <<'PY'
import sqlite3
from web.api.db import resolve_db_path
con = sqlite3.connect(resolve_db_path())
# archive: row present with archived=1; purge: row absent
print("binding:", con.execute(
    "SELECT name, archived FROM binding WHERE name = 'NAME'"
).fetchone())
PY
```

Regression test for the helper itself (uses tmp fixtures, not the live DB):

```bash
cd /home/james/symphony && uv run pytest tests/skills/test_binding_remove.py
```
