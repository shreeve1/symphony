---
id: 070
title: Decompose the run_tick god-function
status: pending
blocked_by: [69]
parent: null
priority: 0
created: 2026-06-17
---

## What to build

Finding L1-01 (`.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`). `run_tick` (`scheduler.py:1168-2050`, ~882 LOC) owns the entire dispatch state machine: reconcile passes, scheduled selection (4 reason branches), reservation, approval/dispatch gates, mode + build-plan recovery, resume prep, render+compaction, run-record lifecycle, agent dispatch with resume-fallback, and 7 terminal-state handlers.

Decompose into a staged pipeline (select → gate → prepare → dispatch → classify-terminal). Lowest-risk increment first: extract the 7 repetitive terminal branches (`_finish_run_record` + `_build_urls` + `_block_issue`/`_notify_review` + `return TickResult`) into a `_classify_terminal` result-handler, then pull the front-half stages. `run_tick` should read as an orchestration story delegating to named stages.

## Acceptance criteria

- [ ] The 7 terminal-state handlers are extracted behind a `_classify_terminal` (or equivalent) result-handler.
- [ ] Front-half stages (select / gate / prepare / dispatch) are named functions `run_tick` delegates to.
- [ ] `run_tick` body is substantially reduced from ~882 LOC; no behavior change.
- [ ] `uv run pytest` passes (full suite green).

## Verification

`uv run pytest`

Highest-risk refactor on the live dispatch path. Before this issue is marked done, James runs the `symphony-restart` skill and confirms `symphony_started`, `reconcile_startup_*`, and `dispatch_completed` in the journal.

## Blocked by

- Blocked by #069 (resume-fallback deduped and cooldown scoped before decomposing the dispatch body).
