---
id: 107
title: Carry blocked_by + locks through the create/patch API (cycle reject)
status: review
blocked_by: [105]
locks: [web-api]
priority: 1
created: 2026-06-23
---

## What to build

Per ADR-0021 (P2 + Update (3)), persist BOTH `issue.blocked_by` and `issue.locks`
through the create/patch API — the path the `/podium-issues` slicer skill (112)
calls. Authoring writes directly to Podium in dependency order, so the slicer
already knows real Podium ids; no kanban-id→Podium-id translation is needed on the
critical path.

- **API** (`web/api/main.py`): add `blocked_by: list[int] | None` and
  `locks: list[str] | None` to `IssueCreate` and the patch model; persist both on
  create/update. Omitted → `[]`.
- **Cycle reject**: reject a `blocked_by` set that introduces a cycle (a→b→a) with
  a clear 400. `locks` need no cycle check (symmetric labels, not edges).
- **No mirror.** Operator confirmed direct-to-Podium with no folder mirroring, so
  there is no kanban-id→Podium-id translation anywhere. The slicer (112) calls this
  API directly in dependency order, so blocker ids are real Podium ids already.

## Acceptance criteria

- [ ] `POST`/patch accept and persist `blocked_by` and `locks`; omitted → `[]`.
- [ ] A `blocked_by` cycle is rejected (API 400), not silently stored.

## Verification

`uv run pytest web/api/tests/test_issue_create.py web/api/tests/test_issue_patch.py -q`
