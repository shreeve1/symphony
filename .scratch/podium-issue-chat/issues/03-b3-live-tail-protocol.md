# 03 — B3: Live-tail protocol (`run.tail` enrichment + new endpoint + run columns)

**What to build:** the `run.tail` WS event gains `run_id`, `source_id`, `from_cursor`, `cursor`, `line_cursors`; a new `GET /api/runs/{id}/tail` returns `{run_id, source_id, from_cursor, cursor, lines, line_cursors}` for the active run only. New `run` columns `agent_session_start_offset` + `source_id` are populated at dispatch. Client catch-up becomes seamless on flyout-open, page reload, and reconnect.

**Blocked by:** None — server-only, foundational for F3.

**Status:** ready-for-agent

- [ ] Add alembic migration `0025_*` adding `agent_session_start_offset` (INTEGER) and `source_id` (TEXT) to the `run` table
- [ ] Extend `_RUN_INSERT_COLUMNS` (`tracker_podium.py`) with the new columns
- [ ] In `start_run_record` (`scheduler/run_records.py`): compute start offset (file size at dispatch for local resumed / 0 otherwise) and `source_id` (agent_session_id + inode) at dispatch time
- [ ] Hoist `row["run_id"]` to the top of `_poll_running`'s loop (`web/api/main.py`) — today only assigned in the remote branch; SQL already selects it
- [ ] Emit complete newline-terminated records only; retain the incomplete suffix without advancing the cursor (fixes the partial-line case)
- [ ] `run.tail` event payload becomes `{type, issue_id, run_id, source_id, from_cursor, cursor, lines, line_cursors}`
- [ ] New `GET /api/runs/{id}/tail` gated `run.state != 'running'` → 404; returns the snapshot using the existing `_read_jsonl_lines` with the same complete-record rule
- [ ] Server stamps nothing new on run rows (run rows are a structured source distinct from the `comments_md` prose stamps)
- [ ] Remote bindings: spool file location consistent with the existing `tail_spool_path`; gated 404 because remote spools are `unlink`ed at cleanup (`agent_runner.py:839–840`)

Verification: `uv run pytest web/api/tests/test_session_tail.py web/api/tests/test_run_endpoints.py tests/test_alembic_baseline.py -q`

Provenance: spec §4, §5, §5.1, §5.2, §5.3, §12.3, §12.4, §12.5.

Wiki refs: [concepts/session-resume-continuity.md], [concepts/podium-tracker.md].
