---
id: 080
title: Issue-liveness reaper core for persistent Claude sessions
status: done
blocked_by: [77]
parent: null
priority: 0
created: 2026-06-17
updated: 2026-06-17
actor: ralph
action_reviewed: 2026-06-17
---

## What to build

A pure sweep function that decides which warm Claude sessions to reap, given a way to read issue state. It never touches an actively-running issue; it reaps terminal/missing issues, parked-idle-past-TTL sessions, and trims a parked max-live cap. Sidecar metadata is the authoritative issue/cwd source.

Source: `plans/warm-claude-session-and-send-keys-steer.md` tasks 6.1–6.3. (Scheduler wiring is #081; boot reaper is #082.)

## What to build (detail)

- Add `sweep_persistent_claude_sessions(binding, *, get_issue, now, idle_ttl_s, max_live)` to `claude_runner.py`: glob `symphony-claude-persist-<binding>-*.sock`; for each, read the task-3.4 metadata sidecar as the AUTHORITATIVE `issue_id`/`binding`/`cwd`/`session_file` (socket-name inverse only as fallback + cross-check; log mismatches). A persist socket with no readable sidecar and no live session is itself an orphan → `cleanup_session()`.
- Per live socket, fetch full issue via `get_issue(issue_id)`:
  - (a) `state == "running"` AND `latest_run_state == "running"` → SKIP (its own loop + `run_timeout_ms` own it).
  - (b) `state` in {`done`, `archived`} or issue not found → `cleanup_session()`.
  - (c) parked (non-running) AND sidecar `session_file` mtime age > `idle_ttl_s` → `cleanup_session()`.
  - (d) else keep.
- Enforce `max_live` over PARKED sessions only: reap the most-idle (oldest `session_file` mtime) beyond the cap; log dropped count + ids (no silent cap).

## Acceptance criteria

- [x] Running issue (state+latest_run_state running) is SKIPPED even with a frozen transcript.
- [x] Terminal (done/archived) or missing issue → reaped.
- [x] Parked + idle past TTL → reaped; parked under TTL → kept; running never idle-reaped.
- [x] `max_live` exceeded over parked sessions → most-idle reaped and logged; running never counted/reaped.
- [x] Worktree session resolves its transcript via the sidecar (not a recomputed cwd).
- [x] Sidecar is authoritative for issue id; lossy socket-name inverse is fallback only.

## Verification

`uv run pytest tests/test_claude_persist.py` and `uv run python -m py_compile claude_runner.py`

## Blocked by

- Blocked by #77 (needs sidecar + `cleanup_session` + naming helpers).

## Implementation Notes

Added `sweep_persistent_claude_sessions` in `claude_runner.py` with sidecar-authoritative issue/session metadata, running-issue skip, terminal/missing cleanup, parked idle TTL cleanup, and parked-only max-live trimming with log output. Added focused reaper tests in `tests/test_claude_persist.py` for running skip, terminal/missing cleanup, idle/fresh parked handling, max-live trimming, sidecar authority, and unreadable-sidecar orphan cleanup. Fresh review returned `RALPH_REVIEW: PASS`.
