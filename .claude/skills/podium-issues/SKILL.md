---
name: podium-issues
description: "Mirror local kanban issues into Podium as one Issue per .kanban file, in the binding that matches the current working directory. Runs after /to-issues; auto-chains when cwd is a Podium binding. DB-direct, no Plane."
---

# Podium Issues

Push the kanban issues `/to-issues` just created into Podium, one Podium Issue
per `.kanban/issues/*.md` file, in the `tracker: podium` binding whose
`repo_path` matches the current working directory.

DB-direct by design: the Podium HTTP API requires a session cookie and only the
bcrypt password hash lives in the environment, so this writes through
`web.api.db` (the same database the running API uses) via the
`web.cli.podium issues import-kanban` command.

## Prerequisites

- Symphony repo at `/home/james/symphony`. Run the CLI from this directory.
- cwd (the binding repo where `.kanban/` lives) must match a `tracker: podium`
  binding in `/home/james/symphony/bindings.yml`. No match → the command exits
  non-zero with the list of available podium bindings. There is no fallback.
- A `.kanban/issues/` directory exists in that repo (produced by `/to-issues`).
- **Ralph worktree caveat.** If `/to-issues` targeted an active Ralph worktree
  (its `.kanban/` lives under `~/<repo>-ralph` on `ralph/run`), the worktree's
  git toplevel does not equal the binding's `repo_path`, so binding resolution
  fails and the mirror is skipped. Mirror from the main repo checkout, or after
  the batch lands. Auto-chaining from `/to-issues` therefore does not mirror
  mid-batch worktree boards.
- Writable Podium DB. With no `PODIUM_DB_PATH` set and `/var/lib/symphony`
  absent, `web.api.db.resolve_db_path()` resolves to the live
  `/home/james/symphony/podium.db`.

## What each issue becomes

- One Podium Issue per kanban file, inserted in **ascending kanban `id`**.
  Podium dispatches todo issues `ORDER BY created_at ASC, id ASC`, so insertion
  order is the dispatch order — issues run chronologically.
- `title` = `[k#NNN] <kanban title>` (the `k#NNN` ties it back to the file).
- `description` = the full kanban body (What to build / Acceptance criteria /
  Verification / Blocked by). `blocked_by` is **advisory text only** — Podium
  has no dependency field and will not gate on it.
- `priority` left NULL (the kanban `priority` integer is intentionally
  dropped); `state` server-set to `todo`; `base_branch`, `preferred_agent`,
  and `approval_required` taken from the binding.
- After each insert the kanban file's frontmatter gains
  `podium_issue_id: <id>` and `podium_binding: <name>`. Files that already carry
  `podium_issue_id` are skipped, so re-runs never duplicate.

## Scope and dispatch consequences — read before a live run

- **Scope is every unmarked file, not just the ones `/to-issues` just created.**
  The command pushes all `.kanban/issues/*.md` lacking a `podium_issue_id`,
  which can include pre-existing issues left on the board. Always dry-run first
  and read the printed list; the count is the number of Podium issues that will
  be created.
- **A live push makes the issues dispatchable immediately.** They land as
  `state=todo`; the scheduler's next poll selects todo issues per binding
  (`tracker_podium.py` `list_issues`) and, for approval-disabled bindings (e.g.
  `homelab`, `approval.enabled: false`), runs them with no gate. Pushing N
  issues queues up to N pi runs. Do not push more than you intend to run.

## Workflow

1. Dry-run (no DB writes, no file mutation):

   ```bash
   cd /home/james/symphony && uv run python -m web.cli.podium issues import-kanban \
     --cwd <binding-repo> --dry-run
   ```

   `--cwd` is the binding repo holding `.kanban/`; defaults to the process cwd.

2. **Standalone invocation** (James runs `/podium-issues` directly): show the
   resolved binding, the planned `k#NNN → title` list, count, and order, and
   call out that every listed issue becomes a `todo` Podium issue that the
   scheduler may dispatch immediately. Confirm with James before the live run.

   **Auto-chained invocation** (called at the end of `/to-issues`): the
   breakdown was already approved in that run, so the just-created issues need
   no re-confirm. But because scope is *all* unmarked files, first compare the
   dry-run pending count against the number `/to-issues` just created. If they
   match, proceed straight to the live run. If pending is larger (a pre-existing
   unmirrored backlog exists), stop and confirm with James before pushing — do
   not silently mirror the backlog.

3. Live run — drop `--dry-run`:

   ```bash
   cd /home/james/symphony && uv run python -m web.cli.podium issues import-kanban \
     --cwd <binding-repo>
   ```

4. Report the `k#NNN → podium #<id>` mapping. Remind that Podium dispatches by
   creation order and does not enforce `blocked_by`.

## Safety rules

- No Plane API calls. No `plane_adapter` imports.
- Do not read or print `/home/james/symphony-host.env`.
- The live run mutates the running infrastructure's `podium.db` and queues real
  scheduler dispatches. Confirm with James for standalone runs; auto-chained
  runs inherit the `/to-issues` approval. When in doubt, dry-run only.
- Leave created Podium issues in place as audit evidence.

## Verification

```bash
cd /home/james/symphony && uv run pytest web/cli/tests/test_podium_issues.py
```
