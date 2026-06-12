---
id: 019
title: Tracker Adapter (Podium) — engine reads/writes Podium store
status: done
blocked_by: [013, 015, 025]
updated: 2026-06-11
actor: ralph
parent: null
priority: 0
created: 2026-06-10
---

## What to build

Implement the Podium side of the Tracker Adapter seam (ADR-0002, ADR-0004,
ADR-0005). Symphony's engine should be able to dispatch against a binding
whose `tracker: podium` declares Podium as the source of truth, without
touching Plane.

Changes:

1. `bindings.yml` schema — add optional `tracker: plane|podium` (default
   `plane` for backwards compatibility). Validate in `config.py`.
2. New module `tracker_podium.py` implements the `TrackerAdapter` protocol
   that `plane_adapter.py` already satisfies. Reads/writes go to the
   Podium SQLite directly (same DB file at `/var/lib/symphony/podium.db`).
3. **SQLite concurrency:** every connection from `tracker_podium.py`
   opens with `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000`.
   The Podium FastAPI process (from #012a) does the same. Two writers
   on the same DB file is supported via WAL; without these pragmas
   SQLITE_BUSY errors will fire under load.
4. **Method parity is enumerated, not greppe**d. The `TrackerAdapter`
   Protocol surface includes (verified from `plane_adapter.py:121-142`):
   - `list_issues(state_filter=...)`
   - `get_issue(issue_id)`
   - `transition_state(issue_id, new_state)`
   - `post_comment(issue_id, body)`
   - `append_context(issue_id, body)` (new method; Plane impl no-ops
     into the comment thread for now)
   - `add_label(issue_id, label)` / `remove_label(issue_id, label)` —
     no-op on Podium (labels dropped); record decision in module docstring.
   - `get_run(run_id)` / `record_run(run_row)` (new; Plane impl skips)
   - other Plane-adapter methods that exist today: enumerate by reading
     `plane_adapter.py` and listing each in this issue's PR description.
   `tracker_podium.PodiumTrackerAdapter` is declared against a
   `@runtime_checkable Protocol TrackerAdapter` in `tracker_adapter.py`
   (new module). The smoke test asserts
   `isinstance(PodiumTrackerAdapter(...), TrackerAdapter)`.
5. ADR-0004 Roles project onto Podium columns:
   - `state:*` → `issue.state` enum values.
   - `mode:*` → `issue.preferred_skill` (Skill→Mode projection table
     lives in `skill_mode_map.py`, added by #025).
   - `agent:*` → `issue.preferred_agent`.
   - For **coding bindings**: `approval-required`, `approved`,
     `scheduled` return "role absent" (those columns do not exist).
   - For **infra bindings** (homelab cutover via #023c): the same three
     Roles project onto new columns added in #023c's Alembic revision
     (`approval_required boolean`, `approved boolean`,
     `scheduled_for timestamp`). #019 ships with the coding-binding
     projection only; infra-binding projection is explicitly deferred
     to #023c and noted in this issue's implementation notes.
6. The renderer's Podium path (added in #025) is the consumer. This slice
   wires it in via `main.py` selecting `PodiumTrackerAdapter` when
   `binding.tracker == "podium"`.
7. **Do not** flip either live binding to Podium in this slice — that
   is #020's cutover work. This slice only proves the adapter works
   against a *test* binding pointed at a temp DB.

## Acceptance criteria

- [x] `bindings.yml` accepts `tracker: podium`; missing field defaults to `plane`; unknown value is a config error.
- [x] `tracker_adapter.py` defines a `@runtime_checkable Protocol TrackerAdapter`; `isinstance(PodiumTrackerAdapter(...), TrackerAdapter)` is True (asserted in test).
- [x] Every method enumerated in step 4 has an implementation in `PodiumTrackerAdapter` AND a dedicated unit test.
- [x] SQLite connections open with `journal_mode=WAL` and `busy_timeout=5000` (assert by inspecting `conn.execute("PRAGMA journal_mode")` and `PRAGMA busy_timeout` return values).
- [x] Concurrent-writer test (`tests/test_podium_sqlite_concurrent.py`): two threads writing to the same DB succeed without SQLITE_BUSY.
- [x] `comments_md` writes via `post_comment(...)` append a structured AI summary block.
- [x] `context_md` writes via `append_context(...)` append the full output blob.
- [x] Engine smoke test (`tests/test_engine_against_podium.py`) wires a binding pointed at an in-memory SQLite Podium DB and exercises a full dispatch cycle (list todo → transition to running → post completion comment → append context → transition to in_review) — no real pi subprocess (mock the agent).
- [x] `tracker_podium.py` does not import `plane_adapter`; no code path writes to Plane (assert via grep).
- [x] Infra-binding role projection is documented as deferred to #023c in the module docstring.

## Verification

```
cd /home/james/symphony && uv run pytest
```

## Implementation Notes

Implemented `tracker: podium` binding configuration, a runtime-checkable tracker protocol, a Podium SQLite tracker adapter, WAL/busy-timeout DB connections, Podium context writes from the scheduler, and regression coverage for method parity, concurrency, and engine dispatch against a temp Podium DB. Infra-binding approval/schedule projection remains deferred to #023c.

Fresh review result: `RALPH_REVIEW: PASS_WITH_NOTES`.

## Blocked by

- #013 (PATCH plumbing exercises the same column writes the adapter performs)
- #015 (Skill catalog grounds the Mode-via-Skill projection)
- #025 (renderer Podium path + Skill→Mode map must exist before adapter wires them in)
