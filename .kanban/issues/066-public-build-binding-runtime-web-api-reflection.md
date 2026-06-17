---
id: 066
title: Promote build_binding_runtime + clean web/api reflection cluster
status: in-progress
blocked_by: [65, 59]
parent: null
priority: 0
created: 2026-06-17
---

## What to build

Findings L0-02 + L0-06 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`). The Podium FastAPI backend reaches engine internals through `vars()` reflection, defeating rename-safety and static analysis. The engine→API dependency direction is correct; only the reflection hack and private status are wrong.

- **L0-02** — rename `_build_binding_runtime` → `build_binding_runtime` (drop underscore); import it normally in `web/api/main.py:957`; document it as the sanctioned single-binding constructor. (Full extraction to a `runtime_factory.py` stays deferred.)
- **L0-06** — replace all four `_compact_issue_context` reflection sites in `web/api/main.py` (`_compact_issue_context` at `:925`): `vars(engine_main)["SymphonyConfig"]` (`:930`) → `from config import SymphonyConfig`; `vars(engine_main)["_build_binding_runtime"]` (`:957`) → the public `build_binding_runtime`; `vars(compaction)["maybe_compact"]` (`:987`) and `vars(compaction)["estimate_tokens"]` (`:1000`) → `from context_compaction import maybe_compact, estimate_tokens`.

Update the ~10 `main.*` monkeypatch references in tests to the public name.

## Acceptance criteria

- [ ] `build_binding_runtime` is public (no leading underscore); `web/api/main.py` imports it normally.
- [ ] `_compact_issue_context` in `web/api/main.py` contains no `vars(engine_main)[...]` or `vars(compaction)[...]`; all four sites use normal imports / the public factory.
- [ ] `grep -n "vars(engine_main)\|vars(compaction)" web/api/main.py` returns nothing.
- [ ] Tests referencing the private factory name are updated to the public name.
- [ ] `uv run pytest` passes.

## Verification

`uv run pytest`

## Blocked by

- Blocked by #065 (probe extracted first so the public factory is pure wiring).
- Blocked by #059 (L0-06 reuses the `context_compaction` normal-import target landed in Phase 1 / L1-05).
