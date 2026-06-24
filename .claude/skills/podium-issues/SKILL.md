---
name: podium-issues
description: "Slice an approved plan directly into Podium Issues for the binding matching cwd. No .kanban scan or mirror; creates issues in dependency order with real blocked_by ids and locks."
---

# Podium Issues

Turn an approved plan into Podium issues directly. This replaces the old
`.kanban` folder mirror: **do not scan or write `.kanban/` files**.

## When to use

Use after `grill-me` / `dev-plan` when the operator wants the plan queued in
Podium instead of Ralph's local kanban.

## Prerequisites

- Run from `/home/james/symphony` or pass `--cwd <binding-repo>` to the CLI.
- cwd must resolve to a `tracker: podium` binding in `bindings.yml` by matching
  the binding `repo_path`.
- No Plane calls. Do not read or print `/home/james/symphony-host.env`.

## Workflow

1. Read the plan from the conversation or the file the operator names.
2. Draft vertical tracer-bullet slices using the `/to-issues` rules:
   - each slice is end-to-end and independently useful;
   - acceptance criteria are objective;
   - verification is a repo-correct runnable command, not prose — slicer-created
     issues are stamped `auto_land=true`, and review backstop re-runs this command;
   - blockers are explicit;
   - `locks` labels identify resources that must not co-run.
3. Show the proposed slices and ask the operator to approve granularity,
   dependencies, locks, and verification commands. This skill is
   authoring-time; do not use it inside unattended dispatch.
4. Write a temporary YAML slice spec, e.g. `/tmp/podium-slices.yml`:

   ```yaml
   slices:
     - key: schema
       title: Add dependency columns
       description: Add the columns and read-path coercion.
       acceptance:
         - issue rows expose blocked_by and locks as typed lists
       verification: uv run pytest web/api/tests/test_alembic_baseline.py -q
       locks: [schema]
     - key: api
       title: Carry dependencies through API
       description: Create/patch accepts blocked_by and locks.
       acceptance:
         - create response includes blocked_by and locks
       verification: uv run pytest web/api/tests/test_issue_create.py -q
       blocked_by: [schema]
       locks: [web-api]
   ```

5. Dry-run:

   ```bash
   cd /home/james/symphony && uv run python -m web.cli.podium issues create-from-plan /tmp/podium-slices.yml --cwd <binding-repo> --dry-run
   ```

6. Live create after approval:

   ```bash
   cd /home/james/symphony && uv run python -m web.cli.podium issues create-from-plan /tmp/podium-slices.yml --cwd <binding-repo>
   ```

7. Spot-check:

   ```bash
   cd /home/james/symphony && uv run python -m web.cli.podium issues list --binding <binding-name>
   ```

## Safety rules

- The live command creates `todo` Podium issues with `auto_land=true` and may make
  them dispatchable on the next scheduler poll. Dry-run first.
- Dependencies are created blocker-first; dependent `blocked_by` uses the real
  Podium ids returned by earlier inserts.
- The old `issues import-kanban` mirror is retired. If you need Ralph local
  issues, use `/to-issues`; if you need Podium issues, use this skill.

## Verification

```bash
PATH="$HOME/.local/bin:$PATH" uv run pytest web/cli/tests/test_podium_issues.py -q
```
