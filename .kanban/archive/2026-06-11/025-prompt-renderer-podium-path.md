---
id: 025
title: prompt_renderer Podium path + Skill→Mode projection
status: done
blocked_by: [012a]
parent: null
priority: 0
created: 2026-06-10
updated: 2026-06-11
actor: ralph
---

## What to build

Pre-slice that prepares `prompt_renderer.py` for #019 (Podium Tracker
Adapter). Today the renderer reads from Plane comment text and resolves
Mode from labels. Podium replaces both surfaces with column reads.

Changes:

1. `prompt_renderer.py` gains a `tracker_kind: Literal["plane", "podium"]`
   parameter on `render_prompt(...)`. Default `"plane"` to preserve current
   call sites.
2. When `tracker_kind == "podium"`:
   - The renderer reads `comments_md` and `context_md` directly from the
     issue payload (which the Podium adapter populates from SQLite —
     #019 provides the data shape).
   - The 12000-char comment-block truncation logic is bypassed for
     Podium (engine-built compaction in #026 handles size separately).
3. **Skill→Mode projection table** lives in a new module
   `skill_mode_map.py` (or appended to `prompt_renderer.py`). The table
   maps known skill names to the legacy Mode enum the renderer still
   uses for prompt variables:
   ```
   "/dev-plan"  → "plan"
   "/dev-build" → "build"
   "/diagnose"  → "execute"   # read-only investigation
   "/code-review" → "execute"
   # default for unknown skills → "execute"
   ```
   Mode is still emitted as a prompt variable (existing template
   contract); when an issue arrives with no `preferred_skill`, Mode
   defaults to `"execute"`.
4. Existing Plane code path (`tracker_kind="plane"`) is unchanged.
5. CONTEXT.md flagged-ambiguity for "Mode scheduled for removal" stays —
   the projection table is the transitional bridge; Mode-the-CONTEXT-term
   retires when both bindings are on Podium.

The Podium adapter (#019) is the consumer of this contract — it calls
`render_prompt(issue, tracker_kind="podium", ...)` and provides the new
issue payload shape (`comments_md`, `context_md`, `preferred_skill`).

## Acceptance criteria

- [x] `prompt_renderer.render_prompt(...)` accepts `tracker_kind` kwarg with default `"plane"`.
- [x] `tests/test_prompt_renderer_podium.py` covers: Podium path reads `comments_md` + `context_md` directly, no truncation; Plane path unchanged (regression).
- [x] `skill_mode_map.SKILL_TO_MODE` is the single source of truth; reverse-lookup is unit-tested for `/dev-plan` → `plan`, `/dev-build` → `build`, `/diagnose` → `execute`, unknown → `execute`.
- [x] Renderer with `tracker_kind="podium"` and a known `preferred_skill` resolves Mode via the map; with `preferred_skill=None`, defaults to `"execute"`.
- [x] `uv run pytest` passes, no regressions on existing Plane renderer tests.
- [x] No changes to `bindings.yml` schema in this slice (that lands in #019).

## Verification

```
cd /home/james/symphony && uv run pytest
```

## Implementation Notes

Implemented `tracker_kind="podium"` in `prompt_renderer.render_prompt(...)`, added `comments_md`, `context_md`, and `preferred_skill` to `IssueData`, and added `skill_mode_map.SKILL_TO_MODE` plus `mode_for_skill(...)` as the transitional Skill→Mode source of truth. Podium comments render through the existing previous-comments block with truncation disabled; Podium Issue Context renders in a dedicated `<issue_context>` block. Plane defaults remain unchanged.

Verification: `uv run pytest` passed (507 passed, 1 skipped). Focused renderer tests and `python3 -m py_compile prompt_renderer.py skill_mode_map.py tests/test_prompt_renderer_podium.py` passed. Fresh review returned `RALPH_REVIEW: PASS`.

LSP note: current Pyright server still reports `reportMissingImports` for `skill_mode_map` in `prompt_renderer.py` and `tests/test_prompt_renderer_podium.py`, but `skill_mode_map.py` is tracked, `python3 -c 'import skill_mode_map'` resolves it from this repo, py_compile passes, and pytest passes. Treated as stale LSP environment noise, not a runtime/import defect.

## Blocked by

- #012a (needs the canonical issue payload shape from the SQLite schema)
