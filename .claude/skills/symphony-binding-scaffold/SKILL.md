---
name: symphony-binding-scaffold
description: "Create a Podium-backed Symphony binding by inserting the binding row in Podium SQLite and appending tracker: podium to bindings.yml. Does not call Plane."
---

# Symphony Binding Scaffold

Create a new Symphony binding for the Podium era.

## Prerequisites

- Symphony repo at `/home/james/symphony`. Run everything from this directory (`skill_migration` is a repo-root module).
- Writable Podium DB path. With no `PODIUM_DB_PATH` set and `/var/lib/symphony` absent, `web.api.db.resolve_db_path()` resolves to the live `/home/james/symphony/podium.db`.
- Target repository exists locally. `WORKFLOW.md` is not required here — `symphony-workflow-author` authors it as a separate step.

## Workflow

1. Resolve binding inputs:
   - `name` — non-empty, no whitespace.
   - `repo_path` — absolute path to the target repo.
   - `base_branch` — e.g. `main`.
   - `default_agent` — must be `pi` or `claude` (default `pi`).
   - `binding_type` — must be `infra` or `coding` (default `coding`).
   - `pi_mode` — `rpc` or `one-shot` (default `rpc`, the accepted ADR-0010 standard). Written only for `pi` bindings; `one-shot` selects the legacy `pi --print` rollback path. Ignored for `claude` bindings.
   - `display_name` — optional; defaults to `name`.
   - `remote_host` / `remote_user` — optional; set both to make this a remote binding (ADR-0012). Use the host name (for example `n8n`), not an IP that requires reverse DNS for display. Writes a `remote:` block to `bindings.yml`, dispatches over SSH, and surfaces the frontend host grouping automatically. `remote_identity` is an optional SSH key path. Remote bindings require `binding_type=coding`, `default_agent=pi`, `pi_mode=rpc` (local coding parity, mirrored from `config.py`); the scaffold raises `ValueError` otherwise.
2. Run `scaffold_podium_binding(...)`. It takes a `PodiumBindingScaffoldRequest` plus required keyword-only `db_path` and `bindings_path`:

   ```bash
   cd /home/james/symphony && uv run python - <<'PY'
   from pathlib import Path
   from web.api.db import resolve_db_path
   from skill_migration import PodiumBindingScaffoldRequest, scaffold_podium_binding

   result = scaffold_podium_binding(
       PodiumBindingScaffoldRequest(
           name="NAME",
           repo_path=Path("/absolute/repo/path"),
           base_branch="main",
           default_agent="pi",      # 'pi' | 'claude'
           binding_type="coding",   # 'infra' | 'coding'
           pi_mode="rpc",           # 'rpc' (default) | 'one-shot'; pi bindings only
           # Remote binding (ADR-0012): set host+user, require RPC pi coding.
           # remote_host="n8n",
           # remote_user="itadmin",
           # remote_identity=None,  # optional SSH key path
       ),
       db_path=resolve_db_path(),
       bindings_path=Path("/home/james/symphony/bindings.yml"),
   )
   print(result)
   PY
   ```

   The call is dupe-guarded: it raises if `name` already exists in the DB or in `bindings.yml`, and schema creation is idempotent (`CREATE TABLE IF NOT EXISTS`).
3. Do not create any tracker-side project. Podium treats the binding itself as the project.
4. The written `bindings.yml` entry includes `plane_project_id: <name>` (transitional `ProjectBinding`/`config.py` compatibility only — not a Plane call and not a real Plane project) and, for `pi` bindings, `pi_mode: rpc` (ADR-0010 accepted; the `pi --mode rpc` dispatch path the live bindings use).
5. New binding is not live until `symphony-host.service` reloads `bindings.yml`. Restart via the `symphony-restart` skill (ask James) when ready, or let `symphony-onboard-project` chain it.
6. **Runtime behavior a new coding binding inherits (no per-binding config needed):**
   - **Worktree-per-run is default-ON for local coding bindings** (ADR-0021 slice 108): each run executes in its own `worktree_dir(repo, binding, issue_id)`, so up to `run_cap` (`SYMPHONY_RUN_CAP`, default 2) independent Issues run in parallel without colliding. Global kill-switch is `SYMPHONY_WORKTREE_DEFAULT` (`config.worktree_default`, default `True`) — not a `bindings.yml` field. Remote bindings keep running in `repo_path` (cap 1; no worktree).
   - **Per-issue review phase + auto-land** (ADR-0023): every coding Issue gets a second (review) run after implement; a passing review on an `auto_land=true` (slicer-authored) Issue merges to base unattended, while operator/UI-created Issues (default `auto_land=false`) park in `in_review` for a manual merge. Infra bindings are excluded from the review phase.

## Safety rules

- No Plane API calls.
- No `plane_adapter` imports.
- Do not read or print `/home/james/symphony-host.env`.
- Show the `bindings.yml` diff before committing (the `plane_project_id` field will appear — see step 4).
- If `bindings.yml` or the DB already contains the binding name, stop instead of merging entries.

## Verification

Confirm your new binding actually landed (replace `NAME`):

```bash
cd /home/james/symphony
uv run python - <<'PY'
import sqlite3
from web.api.db import resolve_db_path
con = sqlite3.connect(resolve_db_path())
print(con.execute("SELECT name, display_name, archived FROM binding WHERE name = 'NAME'").fetchone())
print(con.execute("SELECT binding_name FROM binding_settings WHERE binding_name = 'NAME'").fetchone())
PY
grep -nA10 "name: NAME" bindings.yml
```

Regression test for the helper itself (uses tmp fixtures, not the live DB):

```bash
cd /home/james/symphony && uv run pytest tests/skills/test_binding_scaffold.py
```
