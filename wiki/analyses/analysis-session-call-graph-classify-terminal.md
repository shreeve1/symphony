---
title: "Call-graph trace through `_classify_terminal` — dispatcher spine + repeated blocked-terminal pattern"
type: analysis
status: promoted
created: 2026-07-17
updated: 2026-07-17
sources:
  - scheduler/__init__.py
  - scheduler/tick.py
  - scheduler/loop.py
  - main.py
  - agent_runner.py
  - claude_runner.py
  - session_continuity.py
  - web/api/main.py
  - tests/test_scheduler.py
  - wiki/raw/sessions/2026-07-17-call-graph-trace-classify-terminal.md
confidence: high
tags: [scheduler, call-graph, classify-terminal, refactor, derive-session-id]
---

# Call-graph trace through `_classify_terminal`

A 2026-07-17 interactive session mapped the function-level call graph from `main.run_bindings_loop` down to `session_continuity.derive_session_id`, then audited `_classify_terminal` for repeated blocked-terminal code. The trace was produced by a throwaway AST extractor; the findings here cite live source locations, not the deleted extraction tool. [source: wiki/raw/sessions/2026-07-17-call-graph-trace-classify-terminal.md]

## Dispatcher spine (full call chain, 7 functions / 6 hops / 7 modules)

```text
main.run_bindings_loop                (main.py)
  → scheduler.loop.run_loop           (scheduler/loop.py)
    → scheduler._dispatch_one         (scheduler/__init__.py)
      → scheduler.tick.run_tick       (scheduler/tick.py)
        → scheduler.tick._prepare_run_tick_dispatch
          → scheduler._prepare_resume_candidate
            → session_continuity.derive_session_id    (session_continuity.py:34)
```

Each step confirmed by reading the call site in the source file. [source: `main.py`, `scheduler/loop.py`, `scheduler/__init__.py`, `scheduler/tick.py`, `session_continuity.py`]

`run_tick` itself fans out to **seven immediate callees**: `_new_dispatch_state`, `_select_run_tick_candidate`, `_gate_run_tick_candidate`, `_prepare_run_tick_dispatch`, `_dispatch_run_tick_agent`, `_classify_terminal`, `_release_candidate`. The terminal-state classifier (`_classify_terminal`) sits at the end of this fan-out — every tick produces one `TickResult`. [source: `scheduler/tick.py:568`]

## `derive_session_id()` — 5 production callers (not 38)

The original AST-extracted graph (3,452 nodes / 13,961 edges) tagged `derive_session_id` with betweenness 0.096 across 10 communities. A focused cross-module call-graph extraction (178 Python files, 8,418 resolved call edges, 47% cross-module ratio) narrows the real production callers to **5** — the rest were test-side references to the same name. [source: `wiki/raw/sessions/2026-07-17-call-graph-trace-classify-terminal.md#durable-facts`]

| Caller | Site |
|---|---|
| `agent_runner.run_remote_agent` | `agent_runner.py:631` |
| `agent_runner.run_pi_rpc_agent` | `agent_runner.py:904` |
| `claude_runner.run_claude_agent` | `claude_runner.py:810` |
| `scheduler._prepare_resume_candidate` | `scheduler/__init__.py:285` |
| `web.api.main._SessionTailer.._poll_running` | `web/api/main.py:311` |

The first four are the **dispatcher side**: every agent-run entry point (pi RPC, remote, claude) and the resume-candidate preparer ask `derive_session_id` for a stable session id before launching the subprocess. The fifth is the **FastAPI live-tail side**: `_SessionTailer._poll_running` falls back to `derive_session_id` when `run.agent_session_id` is NULL — covered by `tests/test_session_tail.py:test_tailer_falls_back_when_agent_session_id_null`.

The two sides share `derive_session_id` as a **leaf** but have **zero upstream ancestors in common** in the call graph. This confirms the design: the scheduler and the FastAPI live-tail communicate via on-disk session files keyed by `derive_session_id`, not via in-process calls.

## FastAPI lifespan owns the binding loop

`web.api.main.lifespan()` calls `scheduler.loop.run_loop()` directly as a background task. Direct callees (from `web/api/main.py` lifespan body): `config_from_environment`, `connect`, `ensure_schema`, `seed_if_empty`, `_purge_archived_issues`, `_rows_by_id`, `WebSocketHub..publish`, `scheduler.loop.run_loop`, `_SessionTailer..shutdown`. The FastAPI process is not just an HTTP server — it owns the binding loop. [source: `web/api/main.py`]

## `_classify_terminal` — the 33-callee decision cascade

`scheduler._classify_terminal` (`scheduler/__init__.py:1073`) is a 270-line async function with **33 callees, 17 distinct `TickResult` reason strings, and 13 parameters**. It implements the entire terminal-state machine for agent runs in one cascade. [source: `scheduler/__init__.py:1073-1660`]

### Branch ordering (matters)

1. **Pre-amble** — `binding.resolve_agent` → `_capture_natural_turn` (ADR-0022 / 0037); fallback to `_extract_summary`.
2. **Failure / retry** (if `timed_out or exit_code != 0`) — `_block_retry_ceiling` if retries ≥ MAX; then `_maybe_retry_stall` → `_maybe_transient_review_retry` → `_maybe_retry_transient_implement` (each short-circuits on a hit).
3. **Hard-fail branches** (timeout, nonzero) — `state="failed", verdict="blocked"` + `_block_issue` + notify.
4. **Schedule / permission branches** — `_detect_agent_schedule` then `_parse_schedule_marker` (valid → label + transition + comment; malformed/past → block); `_hit_permission_gate` → block.
5. **Verdict branches** — `_hit_approval_gate` (no verdict) → block; `verdict == "blocked"` → block.
6. **Patrol verified-close** (ADR-0020, `verdict == "done" and binding.auto_close_on_verified and origin == "patrol"`) — direct `transition_state(DONE)`, return `agent-verified-close`.
7. **Question park** — `_extract_question` non-None → `IN_REVIEW` + notify; rate-limit safe via `pending_review_issue_ids`.
8. **Operator reland** (`_handle_operator_reland`) — redispatch or land.
9. **Review verification** (`_handle_review_terminal_done`, ADR-0023) — synthesize review prompt, redispatch.
10. **Clean IN_REVIEW fallthrough** — reason_code = `agent-marker-review` (verdict in {review, done}) or `agent-clean-review` (otherwise).

### The 17 `TickResult` reasons

```
timeout, nonzero,
permission-gate, approval-gate,
agent-marker-blocked, agent-marker-scheduled, agent-scheduled-malformed,
agent-question-park, agent-verified-close, agent-clean-review, agent-marker-review,
agent-blocked, agent-review,
stall-retry, transient-stall-retry, transient-retry-review, transient-implement-retry, transient-retry-implement,
combined-ceiling-exhausted,
agent-crashed, archived-terminal,
operator-reland-terminal, review-terminal-done
```

All 17 are exercised by `tests/test_scheduler.py` (344 defs, the largest test file in the repo). [source: `tests/test_scheduler.py`]

## The repeated blocked-terminal pattern

Six branches share an identical structure (`timeout`, `nonzero`, `permission-gate`, `approval-gate`, `agent-marker-blocked`, and the two `agent-scheduled-malformed` branches):

```python
_stdout, stderr = _format_report(result, secrets)
if summary:
    msg += f"\n\n{summary}"
if stderr:
    msg += f"\n\n{_format_stderr_summary(stderr)}"
await _finish_run_record(adapter, run_id, run_log_path,
    result=result, secrets=secrets,
    state="failed", verdict="blocked",
    summary=summary or msg,  # or branch-specific fallback
    ended_at=now().isoformat())
_iu, _du = _build_urls(config, candidate.id)
await _block_issue(adapter, candidate.id, msg,
    issue_name=candidate.name, issue_identifier=candidate.identifier,
    notifier=notifier, issue_url=_iu, dashboard_url=_du)
return TickResult(True, "<reason>", candidate.id, mode=mode)
```

Each block is ~23 lines. Across `scheduler/__init__.py` alone, the same shape appears 18 times (18 `_block_issue` calls, 27 `_finish_run_record` calls, 24 `_build_urls` calls). The 18 in-file `_finish_run_record` blocks total **410 LOC of structurally-identical code**. [source: `scheduler/__init__.py` (grep counts in raw session capture)]

### `_emit_blocked_terminal` — extraction in progress → committed

An `_emit_blocked_terminal` helper exists in `scheduler/__init__.py:1073` with a `ponytail:` comment attributing the extraction to 6 reason strings. As of 2026-07-17 14:18 UTC the extraction was **partial**: 4 of the 6 sites already converted (`timeout`, `nonzero`, `permission-gate`, `approval-gate`); 2 sites still inline (`agent-marker-blocked`, both `agent-scheduled-malformed` branches). The full extraction saves ~108 LOC; the partial save is ~70 LOC. **This refactor was not started by this session** — it was observed in the working tree at session start.

**Update 2026-07-17 14:21 UTC:** the parallel slice committed `3396c7a refactor(#465): extract _emit_blocked_terminal helper` — all 7 sites now use the helper (lines 1259, 1282, 1333, 1366, 1419, 1446, 1470 in `scheduler/__init__.py`). Net diff: -137 LOC, +136 LOC; the refactor saves ~137 LOC of structurally-identical code. The candidate page's count of "6 reason strings" should be "7" (the two `agent-scheduled-malformed` branches are separate calls with the same reason string but different `now_dt` sources). [source: `scheduler/__init__.py:1073-1116` (definition), `scheduler/__init__.py:1259,1282,1333,1366,1419,1446,1470` (all call sites), commit `3396c7a`]

## Architectural notes

- **The function is essentially a finite-state machine encoded as a Python cascade.** Each branch short-circuits with a `TickResult` or falls through. ADR-0016, ADR-0017, ADR-0022 added ordering constraints (natural-turn capture first, gates before verifications) — the cascade's ordering encodes the policy.
- **The repeated blocked-terminal blocks are not a behavioral duplication, they are a structural one.** Each block must preserve: (a) the exact `TickResult` reason string, (b) the exact fallback summary text (visible to operators in the comment), (c) the `now()` evaluation order. A clean refactor must thread `ended_at` explicitly because the two `agent-scheduled-malformed` branches use a pre-computed `now_dt` (for the past-not-before error), not `now()`.
- **47% cross-module call density** in the resolver-built call graph. Top cross-module edges: `web → plane_adapter` (527), `tests → scheduler` (323), `tests → agent_runner` (308). The legacy Plane adapter still dominates the API layer even after the Podium cutover.

## Why the original AST graph over-counted

The graphify AST extractor produced 4,452 nodes / 13,961 edges with the report tagging `derive_session_id` as a top "betweenness" node. The cross-module resolver-built call graph (178 Python files, 8,418 calls, 47% cross-module ratio) showed:

- `derive_session_id` has 5 production callers, not 38
- `SymphonyConfig` is a structural hub (178 references / uses / imports), not a procedural one (only 2 actual constructor calls)
- The real procedural hubs are `_classify_terminal` (33 callees), `run_claude_agent` (30), `run_remote_agent` (29), `_poll_claude_until_done` (19)

The AST extractor without a type resolver cannot match bare function calls across module boundaries; the result is a structurally-correct but procedurally-thinned graph. Live source citations (this page) are the durable artifact; the call-graph JSON is intentionally not committed.

## Citations

- `wiki/raw/sessions/2026-07-17-call-graph-trace-classify-terminal.md`
- `scheduler/__init__.py` (lines 285, 1073-1660)
- `scheduler/tick.py` (line 568)
- `scheduler/loop.py`
- `main.py`
- `agent_runner.py` (lines 631, 904)
- `claude_runner.py` (line 810)
- `session_continuity.py` (line 34)
- `web/api/main.py` (line 311, lifespan body)
- `tests/test_scheduler.py`
