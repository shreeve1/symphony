---
type: analysis
title: Skill Source PermissionError Dispatch Crash (2026-07-06)
status: promoted
created: 2026-07-06
updated: 2026-07-06
sources:
  - wiki/raw/sessions/2026-07-06-skill-source-permission-error-dispatch-crash.md
  - tracker_podium.py
  - scheduler/__init__.py
confidence: high
tags:
  - scheduler
  - dispatch
  - skill-catalog
  - bug
---

# Skill Source PermissionError Dispatch Crash

## Summary

Two bugs conspired to crash dispatch for the symphony binding, leaving issues stuck in `todo` and `blocked` states:

1. `tracker_podium.py:skill_source()` had a non-deterministic query (`SELECT source FROM skill WHERE name = ?` with no `ORDER BY`) that could pick a stale row from a different host, returning an inaccessible path like `/home/itadmin/.claude/skills/.../SKILL.md`.

2. Python 3.12 `pathlib.Path.is_file()` raises `PermissionError` (does not return `False`) when the parent directory is unreadable. The dispatch gate in `_apply_dispatch_gate` called `Path(skill_source).is_file()` unguarded, crashing the entire tick instead of returning a block reason.

## Root Cause Chain

1. Remote-host skill rows (`host=100.95.224.218`) leak into the local Podium DB via the per-host skill catalog sync
2. `skill_source()` picks the first matching row — non-deterministic without `ORDER BY`
3. That row points to `/home/itadmin/...` (inaccessible from `aidev`)
4. `Path.is_file()` raises `PermissionError` instead of returning `False`
5. Exception propagates unhandled through `_apply_dispatch_gate` → `run_tick` → `_dispatch_one`, logging `dispatch_failed`
6. Issue state may be corrupted: `blocked` if the gate crashed before claiming, or `running` with an orphaned Run row if the crash happened after claim

## Impact

- 2 symphony binding issues stuck (#258 blocked, #265 running with orphaned run 984)
- 49 remote-host skill rows in the DB, any of which could trigger the crash when an issue referenced a skill that also existed on the remote host

## Fix

### Code (commit `110b324`)

- `tracker_podium.py`: `skill_source()` now `ORDER BY CASE WHEN binding_name = ? THEN 0 WHEN binding_name IS NULL THEN 1 ELSE 2 END, id` — deterministic, prefers binding-scoped skills
- `scheduler/__init__.py`: `_apply_dispatch_gate` wraps `Path.is_file()` in `try/except PermissionError`, returning a gate block reason instead of crashing

### Data

- Deleted 49 stale rows from the `skill` table where `host = '100.95.224.218'`

## Verification

- Journal confirmed no further `dispatch_failed` after restart with fixes
- Issue #258 dispatched and resumed successfully at 00:41:37
- Issue #265 queued behind run cap (expected)

## Open Questions

- Should the skill sync filter out or skip remote-host skills when the source path is inaccessible from the local host?
- Should the startup reconciler detect and clean up `running` Run rows whose agent process never started? (Run 984 was created, the agent never ran, but the reconciler swept before the dispatch — timing window)

## Citations

- Raw session: [wiki/raw/sessions/2026-07-06-skill-source-permission-error-dispatch-crash.md](/wiki/raw/sessions/2026-07-06-skill-source-permission-error-dispatch-crash.md)
- Code fix: commit `110b324` — `fix(scheduler): PermissionError crash on inaccessible skill source`
- Evidence: `journalctl -u symphony-host.service` — `dispatch_failed error=[Errno 13] Permission denied: '/home/itadmin/.claude/skills/podium-issues/SKILL.md'`
