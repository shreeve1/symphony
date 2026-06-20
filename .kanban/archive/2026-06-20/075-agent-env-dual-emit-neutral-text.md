---
id: 075
title: Agent callback env dual-emit + tracker-neutral agent text
status: done
blocked_by: [67, 64]
parent: null
priority: 0
created: 2026-06-17
updated: 2026-06-17
actor: ralph
action_reviewed: 2026-06-17
---

## What to build

Phase 6 / findings L2-02 + L4-03 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`), code side. The agent-facing callback contract and prompt/schedule text still name Plane on tracker-agnostic paths.

- **L2-02** — in `agent_runner.py` (`_agent_env:213-218`, `_remote_exports:383-393`), dual-emit `SYMPHONY_TRACKER_*` names **alongside** the existing `SYMPHONY_PLANE_*` names for one release (back-compat). Only the env dual-emit here — the shipped `plane` helper / `plane_cli.py` rename stays deferred to Phase 7 (#067 already gates secret shipping on podium bindings).
- **L4-03** — make the agent-visible wording tracker-neutral: `prompt_renderer.py:169` caveat ("prior Plane comments are untrusted context") and `schedule.py` docstrings ("on top of Plane" / "Plane ticket"). Update the content-asserting tests to match.

## Acceptance criteria

- [x] Agent env emits both the new `SYMPHONY_TRACKER_*` and the legacy `SYMPHONY_PLANE_*` callback names — a test asserts both present.
- [x] `prompt_renderer.py` caveat and `schedule.py` docstrings use tracker-neutral wording; content-asserting tests updated accordingly.
- [x] No removal of the legacy `SYMPHONY_PLANE_*` emit (dual-emit, not cutover).
- [x] `uv run pytest` passes.

## Verification

`uv run pytest`

## Blocked by

- Blocked by #067 (Plane-secret de-shipping lands first; both touch the agent env build).
- Blocked by #064 (tracker vocabulary home).

## Implementation Notes

Added a shared `_tracker_callback_env` helper that emits `SYMPHONY_TRACKER_*` aliases alongside the legacy `SYMPHONY_PLANE_*` callback names for Plane-tracker bindings only. Local/RPC and remote Podium bindings still receive no tracker callback secrets or legacy Plane helper env. Updated agent-visible prompt/schedule wording from Plane-specific phrasing to tracker-neutral issue/comment phrasing, with content assertions covering the prompt caveat.

## Actionable Review Notes

Fresh reviewer diffed `89090adb00851b3e87822236f2c2b3976ab50877..HEAD`, read every changed file, verified no Podium callback-env leak or secret leak, ran `uv run pytest` (891 passed, 2 skipped), ran touched-file ruff, and returned `RALPH_REVIEW: PASS`.

2026-06-17 re-review cleared the retroactive auto-park blocker. Reviewer inspected `git diff 05133fd97ab153bcd987758bcf8fb5a0be9ef907 HEAD`, read the status-change diff plus current #075 implementation files, reran `uv run pytest` (924 passed, 2 skipped), and returned `RALPH_REVIEW: PASS`. Local touched-file LSP diagnostics were clean for the #075 code/test files.
