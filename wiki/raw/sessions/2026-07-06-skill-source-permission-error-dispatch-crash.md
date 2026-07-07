# Session Capture: Skill Source PermissionError Dispatch Crash

- Date: 2026-07-06
- Purpose: Diagnose and fix symphony binding issues stuck in todo not being dispatched
- Scope: Root cause analysis, code fix, data cleanup, verification

## Durable Facts

- Python 3.12 `pathlib.Path.is_file()` raises `PermissionError` (not returning `False`) when the parent directory is unreadable — Evidence: Python 3.12.3 on aidev, reproduced in-session
- `tracker_podium.py:skill_source()` query `SELECT source FROM skill WHERE name = ?` had no `ORDER BY`, making row selection non-deterministic across hosts — Evidence: `tracker_podium.py` line 153, confirmed with DB query showing 3 rows for `podium-issues` with different hosts
- Remote-host skill rows (`host=100.95.224.218`) from the skill catalog sync can leak into the local Podium DB and interfere with dispatch when the non-deterministic query picks them over local skills — Evidence: 49 rows deleted from `podium.db` skill table, host `100.95.224.218`
- The symphony binding had 2 issues stuck: #258 (blocked) and #265 (running, orphaned run) — both caused by the PermissionError crash in `_apply_dispatch_gate`

## Decisions

- `skill_source()` made deterministic: `ORDER BY CASE WHEN binding_name = ? THEN 0 WHEN binding_name IS NULL THEN 1 ELSE 2 END, id` — prefers binding-scoped, then global, then by id — Evidence: commit `110b324`
- `_apply_dispatch_gate` now wraps `Path(skill_source).is_file()` in try/except PermissionError, returning a gate block reason instead of crashing — Evidence: commit `110b324`
- 49 stale remote-host skill rows deleted from `podium.db` — Evidence: in-session SQL DELETE

## Evidence

- Journal: `journalctl -u symphony-host.service --since "2 hours ago"` — `dispatch_failed error=[Errno 13] Permission denied: '/home/itadmin/.claude/skills/podium-issues/SKILL.md'`
- Code: `scheduler/__init__.py` line 694, `_apply_dispatch_gate` — `Path(skill_source).is_file()` unguarded
- Code: `tracker_podium.py` line 153, `skill_source()` — non-deterministic query
- DB: `podium.db` skill table — 49 rows with `host='100.95.224.218'`, `source LIKE '/home/itadmin/%'`
- Fix: commit `110b324` — `fix(scheduler): PermissionError crash on inaccessible skill source`

## Exclusions

- Full session transcript not captured
- No secrets or credentials involved

## Open Questions And Follow-Ups

- Should the skill sync filter out remote-host skills when the source path is inaccessible from the local host?
- Should the startup reconciler detect and clean up orphaned `running` runs created by crashed dispatches? (Run 984 was created, agent never ran, but reconciler ran before the dispatch — timing window)
