---
id: 089
title: "Scaffold: stop emitting infra WORKFLOW.md (ADR-0016)"
status: pending
blocked_by: []
parent: null
priority: 0
created: 2026-06-20
---

## What to build

Remove the per-repo `WORKFLOW.md` emission from the (dormant Plane) project scaffold, per ADR-0016 group 4. The live Podium scaffold (`skill_migration.scaffold_podium_binding`) already does not write a `WORKFLOW.md`, so no Podium change is needed — this is the Plane path in `project_scaffold.py`.

Source plan: `plans/adr-0016-workflow-md-renderer-constant.md` (group 4).

- In `project_scaffold.py` remove: the `WORKFLOW_STUB` constant (`:50-66`), the `_write_workflow_stub` call (`:295-296`), the `_write_workflow_stub` function (`:450`), the "WORKFLOW.md already exists" guards (`:363`, `:452`), the `workflow_stub`/`workflow_output_path`/`workflow_allow_overwrite` parameters, the `ProjectScaffoldResult.workflow_path` field, and the CLI `.WORKFLOW.md.preview` block (`:517-522`). Keep all edits self-consistent (no dangling references).
- Update `tests/test_project_scaffold.py` for the removed emission / preview / result field.
- Cheap guard (acceptance): confirm no `WORKFLOW.infra.md` template or `symphony-workflow-author` skill remain in the repo (they were already absent — found only in `~/.local/share/Trash/`). If present anywhere in-repo, remove them.

Disjoint files from issue 088 (parallel-safe). Do NOT touch `prompt_renderer.py`, `main.py`, or the homelab repo.

## Acceptance criteria

- [ ] `project_scaffold.py` no longer defines `WORKFLOW_STUB` or `_write_workflow_stub`, takes no workflow params, and `ProjectScaffoldResult` has no `workflow_path` field.
- [ ] Running the Plane scaffold path creates no `WORKFLOW.md` and no `.WORKFLOW.md.preview` artifact.
- [ ] `grep -rn "WORKFLOW_STUB\|_write_workflow_stub\|workflow_path\|WORKFLOW.md.preview" project_scaffold.py` returns nothing.
- [ ] `grep -rln "WORKFLOW.infra.md" . | grep -v .venv | grep -v Trash` returns nothing; no `symphony-workflow-author` dir under `.claude/skills/`.
- [ ] `tests/test_project_scaffold.py` updated and passing.
- [ ] Full suite green.

## Verification

`uv run python -m py_compile project_scaffold.py && uv run pytest tests/test_project_scaffold.py -q && uv run pytest -q`

## Blocked by

None — can start immediately (parallel-safe with #088).
