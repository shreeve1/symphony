---
id: 071
title: Split scheduler.py into a scheduler/ package
status: pending
blocked_by: [70]
parent: null
priority: 0
created: 2026-06-17
---

## What to build

Finding L1-03 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`). `scheduler.py` is 3039 LOC mixing many cohesive concerns: marker parsing (`:192-393`), report sanitization + secret redaction (`:404-528`), run-record lifecycle (`:892-1006`), candidate selection/reservation (`:2520-2627`), schedule handling (`:2630-2843`), reconcilers (`:2090-2296`), dispatch loop (`:2387-2510`), and `run_tick`.

Split into a `scheduler/` package — `markers.py`, `sanitize.py`, `run_records.py`, `selection.py`, `schedule.py`, `reconcile.py`, `loop.py`, `tick.py` + `__init__.py` re-exporting the public surface. Start with the pure leaves (`markers`, `sanitize`). The `__init__` re-export must preserve `from scheduler import run_loop, reconcile_startup, _resolve_mode` (`main.py:38`) and the full test-suite import surface. Lands after #070 so `tick.py` arrives already-decomposed.

## Acceptance criteria

- [ ] `scheduler/` package exists with the concern-split modules above and an `__init__.py` re-export.
- [ ] `from scheduler import run_loop, reconcile_startup, _resolve_mode` resolves unchanged.
- [ ] Every existing `scheduler.*` import across the repo and tests resolves via the `__init__` re-export.
- [ ] Import graph stays acyclic (no cycle between the new submodules).
- [ ] `uv run pytest` passes.

## Verification

`uv run pytest`

Largest structural change on the live dispatch path. Before this issue is marked done, James runs the `symphony-restart` skill and confirms `symphony_started`, `reconcile_startup_*`, and `dispatch_completed` in the journal.

## Blocked by

- Blocked by #070 (decompose `run_tick` before relocating it to `tick.py`).
