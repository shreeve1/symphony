---
id: 089
title: "Scaffold: stop emitting infra WORKFLOW.md (ADR-0016)"
status: done
blocked_by: []
parent: null
priority: 0
created: 2026-06-20
updated: 2026-06-21
---

> **Closed 2026-06-21:** already implemented in a prior session — commit `7e71b10`. Verified: `WORKFLOW_STUB`/`_write_workflow_stub`/`workflow_path` removed from `project_scaffold.py`; `symphony-workflow-author` skill absent and test refs reconciled.

## What to build

Remove the per-repo `WORKFLOW.md` emission from the (dormant Plane) project scaffold, per ADR-0016 group 4. The live Podium scaffold (`skill_migration.scaffold_podium_binding`) already does not write a `WORKFLOW.md`, so no Podium change is needed — this is the Plane path in `project_scaffold.py`.

Source plan: `plans/adr-0016-workflow-md-renderer-constant.md` (group 4).

- In `project_scaffold.py` remove: the `WORKFLOW_STUB` constant (`:50-66`), the `_write_workflow_stub` call (`:295-296`), the `_write_workflow_stub` function (`:450`), the "WORKFLOW.md already exists" guards (`:363`, `:452`), the `workflow_stub`/`workflow_output_path`/`workflow_allow_overwrite` parameters, the `ProjectScaffoldResult.workflow_path` field, and the CLI `.WORKFLOW.md.preview` block (`:517-522`). Keep all edits self-consistent (no dangling references).
- Update `tests/test_project_scaffold.py` for the removed emission / preview / result field.
- **Reconcile the skill tests (pi review — NOT doc-only).** The `symphony-workflow-author` skill dir is already absent from `.claude/skills/`, but three skill tests still reference it: `tests/skills/test_workflow_author.py:6` (`SKILL_PATH = Path(".claude/skills/symphony-workflow-author/SKILL.md")`), `tests/skills/test_onboard_project.py:13` and `tests/skills/test_restart_troubleshooter.py:34` (`assert "symphony-workflow-author" in text`). Retiring the skill means: delete `test_workflow_author.py`, and remove the `symphony-workflow-author` assertions from the other two (or repoint to whatever replaced it). If a live skill copy exists elsewhere, delete it and the `symphony-onboard-project` branch invoking it. Net: no skill test references a non-existent `symphony-workflow-author`.
- Confirm no `WORKFLOW.infra.md` template remains in-repo (was found only in `~/.local/share/Trash/`).

Disjoint source files from issue 088 (parallel-safe), but both touch the test suite — run the full suite at the end. Do NOT touch `prompt_renderer.py`, `main.py`, or the homelab repo.

## Acceptance criteria

- [ ] `project_scaffold.py` no longer defines `WORKFLOW_STUB` or `_write_workflow_stub`, takes no workflow params, and `ProjectScaffoldResult` has no `workflow_path` field.
- [ ] Running the Plane scaffold path creates no `WORKFLOW.md` and no `.WORKFLOW.md.preview` artifact.
- [ ] `grep -rn "WORKFLOW_STUB\|_write_workflow_stub\|workflow_path\|WORKFLOW.md.preview" project_scaffold.py` returns nothing.
- [ ] `grep -rln "WORKFLOW.infra.md" . | grep -v .venv | grep -v Trash` returns nothing; no `symphony-workflow-author` dir under `.claude/skills/`.
- [ ] `grep -rn "symphony-workflow-author" tests/` returns nothing (the 3 skill tests reconciled).
- [ ] `tests/test_project_scaffold.py` updated and passing.
- [ ] Full suite green (no NEW failures vs the #088 baseline; the reconciled skill tests no longer error on the missing skill).

## Verification

`uv run python -m py_compile project_scaffold.py && uv run pytest tests/test_project_scaffold.py -q && uv run pytest -q`

## Blocked by

None — can start immediately (parallel-safe with #088).
