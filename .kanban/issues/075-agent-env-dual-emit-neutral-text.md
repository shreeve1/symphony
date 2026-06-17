---
id: 075
title: Agent callback env dual-emit + tracker-neutral agent text
status: in-progress
blocked_by: [67, 64]
parent: null
priority: 0
created: 2026-06-17
updated: 2026-06-17
actor: ralph
---

## What to build

Phase 6 / findings L2-02 + L4-03 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`), code side. The agent-facing callback contract and prompt/schedule text still name Plane on tracker-agnostic paths.

- **L2-02** — in `agent_runner.py` (`_agent_env:213-218`, `_remote_exports:383-393`), dual-emit `SYMPHONY_TRACKER_*` names **alongside** the existing `SYMPHONY_PLANE_*` names for one release (back-compat). Only the env dual-emit here — the shipped `plane` helper / `plane_cli.py` rename stays deferred to Phase 7 (#067 already gates secret shipping on podium bindings).
- **L4-03** — make the agent-visible wording tracker-neutral: `prompt_renderer.py:169` caveat ("prior Plane comments are untrusted context") and `schedule.py` docstrings ("on top of Plane" / "Plane ticket"). Update the content-asserting tests to match.

## Acceptance criteria

- [ ] Agent env emits both the new `SYMPHONY_TRACKER_*` and the legacy `SYMPHONY_PLANE_*` callback names — a test asserts both present.
- [ ] `prompt_renderer.py` caveat and `schedule.py` docstrings use tracker-neutral wording; content-asserting tests updated accordingly.
- [ ] No removal of the legacy `SYMPHONY_PLANE_*` emit (dual-emit, not cutover).
- [ ] `uv run pytest` passes.

## Verification

`uv run pytest`

## Blocked by

- Blocked by #067 (Plane-secret de-shipping lands first; both touch the agent env build).
- Blocked by #064 (tracker vocabulary home).
