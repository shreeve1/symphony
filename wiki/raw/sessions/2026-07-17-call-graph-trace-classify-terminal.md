# Session Capture: Call-graph trace through `_classify_terminal`

- Date: 2026-07-17
- Purpose: Map the function-level call graph from `main.run_bindings_loop` to `session_continuity.derive_session_id`, then audit `_classify_terminal` for the repeated blocked-terminal pattern. Findings feed a candidate analysis page; an in-progress `_emit_blocked_terminal` extraction in `scheduler/__init__.py` was observed, not authored by this session.
- Scope: Captured facts and decisions from one interactive graphify + call-graph trace session. Excludes the parallel ralph slice (issue 127, worktree_active) that is concurrently editing `web/api/main.py`, `web/frontend/app/[binding]/automations/page.tsx`, and `bindings.yml`.

## Durable Facts

- **`session_continuity.derive_session_id()` has 5 production callers (not 38 as the AST graph implied).** Production call sites, all confirmed against live source:
  - `agent_runner.run_remote_agent` at `agent_runner.py:631`
  - `agent_runner.run_pi_rpc_agent` at `agent_runner.py:904`
  - `claude_runner.run_claude_agent` at `claude_runner.py:810`
  - `scheduler._prepare_resume_candidate` at `scheduler/__init__.py:285`
  - `web.api.main._SessionTailer.._poll_running` at `web/api/main.py:311`
  - (Plus 4 test callers in `web/api/tests/test_session_tail.py`.) — Evidence: `agent_runner.py`, `claude_runner.py`, `scheduler/__init__.py`, `web/api/main.py`
- **The full dispatcher call spine (`main.run_bindings_loop` → `session_continuity.derive_session_id`) is 7 functions / 6 hops / 7 distinct modules.** The chain is: `main.run_bindings_loop` → `scheduler.loop.run_loop` → `scheduler._dispatch_one` → `scheduler.tick.run_tick` → `scheduler.tick._prepare_run_tick_dispatch` → `scheduler._prepare_resume_candidate` → `session_continuity.derive_session_id`. — Evidence: `main.py`, `scheduler/loop.py`, `scheduler/__init__.py`, `scheduler/tick.py`, `session_continuity.py`
- **`web.api.main.lifespan()` calls `scheduler.loop.run_loop()` directly.** The FastAPI process owns the binding loop as a background task — it is not just an HTTP server. — Evidence: `web/api/main.py` (callees of `lifespan`)
- **`scheduler._classify_terminal` is a 270-line async decision cascade with 33 callees, 17 distinct `TickResult` reason strings, and 13 parameters.** The function is the central terminal-state machine: every agent run passes through it exactly once per tick. — Evidence: `scheduler/__init__.py:1073-1660`
- **The blocked-terminal pattern (`_format_report` → `_finish_run_record(state="failed", verdict="blocked")` → `_build_urls` → `_block_issue` → `TickResult(reason)`) repeats 6 times in `_classify_terminal`.** Reasons: `timeout`, `nonzero`, `permission-gate`, `approval-gate`, `agent-marker-blocked`, and the two `agent-scheduled-malformed` branches (past-not-before + malformed). — Evidence: `scheduler/__init__.py:1207-1486`
- **An `_emit_blocked_terminal(reason, msg, fallback_summary, summary, ended_at, ...)` extraction is in flight in `scheduler/__init__.py`** (4 of the 6 sites already converted as of 2026-07-17 14:18 UTC; the remaining sites — `agent-marker-blocked`, the two `agent-scheduled-malformed` branches — still use the inline pattern). This refactor was not started by this session; it was observed in the working tree. **Update 2026-07-17 14:21 UTC:** the parallel slice committed `3396c7a refactor(#465): extract _emit_blocked_terminal helper` — all 7 sites now use the helper (lines 1259, 1282, 1333, 1366, 1419, 1446, 1470 in `scheduler/__init__.py`). Net: -137 LOC, +136 LOC; the diff saves ~137 LOC of structurally-identical code. — Evidence: `scheduler/__init__.py:1073-1116` (definition), `scheduler/__init__.py:1259, 1282, 1333, 1366, 1419, 1446, 1470` (all call sites), commit `3396c7a`.
- **Across the whole scheduler package, the same repeated helpers appear 28+ times:** 18 `_block_issue` calls in `scheduler/__init__.py` alone, 27 `_finish_run_record` calls, 24 `_build_urls` calls. The 18 in-file `_finish_run_record` blocks total 410 LOC; each is ~23 lines of structurally-identical code. — Evidence: `scheduler/__init__.py` (grep)

## Decisions

- **Will NOT commit a custom AST call-graph extractor as a tracked tool.** A throwaway `.graphify_call_graph.py` was written to produce the cross-module call graph for this session's analysis, then deleted. It had a real correctness flaw: its simple-name fallback arbitrarily picked the first matching definition, which would emit false edges if reused. Live source citations are the durable artifact, not the derived JSON. (Advisor call 2026-07-17 surfaced this.)
- **Will commit `.gitignore` change to exclude `graphify-out/`.** Knowledge-graph build artifacts are regenerated per run; tracked source files are the input surface. This is the same pattern as `wiki/.gate-state.json` (already gitignored) and `podium.db` (already gitignored).
- **Wiki-update obligation triggered.** Per `CLAUDE.md` "Maintenance Trigger": this session produced durable architecture knowledge (the dispatcher-spine call graph, the `_classify_terminal` decision cascade, the repeated blocked-terminal pattern, and an observation of an in-progress refactor). The candidate analysis page must cite live source locations, not the deleted `.call_graph.json`.

## Evidence

- `agent_runner.py` (lines 631, 904 — derive_session_id callsites)
- `claude_runner.py:810` — run_claude_agent → derive_session_id
- `scheduler/__init__.py:1073-1660` — _classify_terminal source
- `scheduler/__init__.py:1073-1116` — _emit_blocked_terminal definition (in-progress refactor, not authored by this session)
- `scheduler/__init__.py:285` — _prepare_resume_candidate → derive_session_id
- `web/api/main.py:311` — _SessionTailer.._poll_running → derive_session_id
- `web/api/main.py:lifespan()` — calls `scheduler.loop.run_loop`
- `main.py` — entry run_bindings_loop
- `scheduler/loop.py` — run_loop
- `scheduler/tick.py` — run_tick + _prepare_run_tick_dispatch
- `session_continuity.py:34` — derive_session_id definition
- `tests/test_scheduler.py` — TickResult reason-string assertions (test coverage of the 17 reasons)

## Exclusions

- The raw graph HTML + report in `graphify-out/` (kept on disk but gitignored).
- Pre-existing dirty files unrelated to this session: `bindings.yml`, `plans/.patrol-incident-dedup-and-bounded-history.state.yml`, `web/frontend/app/[binding]/automations/page.tsx`, `web/frontend/tests/automations.spec.ts` (Ralph slice #127 worktree_active).
- The full deleted `.graphify_call_graph.py` AST extractor — superseded by direct source citations.
- The first ~5 turns of the graphify output that showed AST graph inflated counts (corrected inline).
- Secrets, credentials, run IDs from `.symphony-runs/` — referenced only by path, not content.

## Open Questions And Follow-Ups

- **Who is editing `scheduler/__init__.py`?** The `_emit_blocked_terminal` extraction was not started by this session but appeared in the working tree at 14:18 UTC. The active ralph slice is on issue 127 (worktree_active), which doesn't touch `scheduler/__init__.py`. The parallel slice landed as commit `3396c7a refactor(#465): extract _emit_blocked_terminal helper` at 14:21 UTC (3 minutes after this session observed the partial refactor). It appears to be issue #465 — a second parallel slice not listed in `.kanban/issues/` as of this session.
- **When does the second part of the `_emit_blocked_terminal` extraction land?** Already landed — commit `3396c7a` (2026-07-17 14:21 UTC) converts all 7 sites.
- **Should the same `_emit_*_terminal` pattern apply to the success branches?** The `agent-clean-review` / `agent-marker-review` / `agent-question-park` branches repeat a similar `_finish_run_record(state="succeeded", verdict="review")` + `add_comment` + `transition_state(IN_REVIEW)` + `_notify_review` block, but with different shape (no `_block_issue`, different state, different side effects). A second helper would save ~40 LOC; the case for it is weaker than for `_emit_blocked_terminal` because the success branches have less repetition (3 sites vs 6).
