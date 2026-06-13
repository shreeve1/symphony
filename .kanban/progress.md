# Ralph Progress Log

This file tracks implementation notes across Ralph iterations.

# Conventions & Decisions

- Runtime `SCHEMA_SQL` and Alembic head must stay in parity; fresh DBs must stamp `INITIAL_REVISION` to the latest migration head.

# Iteration Log

## #047 Run-row session-tracking columns — 2026-06-13

**What changed:** Added run-table session tracking columns for Session Resume continuity: `agent_session_sha TEXT` and `resumed BOOLEAN DEFAULT FALSE`.
**Files:** `web/api/schema.py`, `web/api/migrations/versions/0007_add_run_session_tracking_columns.py`, `.kanban/issues/047-run-session-tracking-columns.md`.
**Decisions:** Kept scope schema-only; no scheduler, adapter, or prompt changes in this slice. Used SQLite-compatible `BOOLEAN DEFAULT FALSE`, consistent with existing Podium boolean columns.
**Conventions established:** New schema columns require both an Alembic revision and `SCHEMA_SQL` parity, plus `INITIAL_REVISION` bump for fresh DB stamping.
**Notes for next iteration:** #048 and #049 can proceed independently; downstream resume wiring should write `agent_session_sha` and `resumed` into Run rows.

## #048 Continuity decision core — 2026-06-13

**What changed:** Added the pure Session Resume decision module with deterministic session ids, agent session-file path resolution, and resume eligibility decisions.
**Files:** `session_continuity.py`, `tests/test_session_continuity.py`, `.kanban/issues/048-continuity-decision-core.md`.
**Decisions:** Used derived UUIDv5 ids from `symphony.issue:<issue_id>` and kept this slice free of scheduler, subprocess, and network imports. Pi session lookup honors `PI_CODING_AGENT_SESSION_DIR` and finds timestamp-prefixed session files.
**Conventions established:** Resume decision reasons are stable string constants (`agent-mismatch`, `cwd-missing`, `session-absent`, `sha-drift`) suitable for future scheduler log markers.
**Notes for next iteration:** #049 can build the delta-only prompt independently; #050/#051 should consume `derive_session_id`, `session_file_path`, and `evaluate_resume_eligibility` rather than duplicating predicate logic.

## #049 Delta-only resume prompt rendering — 2026-06-13

**What changed:** Added resume-mode prompt rendering so resumed runs receive only the shared output contract plus the newest `### Operator Reply` delta.
**Files:** `prompt_renderer.py`, `tests/test_prompt_renderer_podium.py`, `.kanban/issues/049-delta-only-resume-prompt.md`.
**Decisions:** Resume prompts intentionally omit WORKFLOW.md, issue description, full comments, and issue context; the Podium `preferred_skill` directive still prepends resume prompts when set.
**Conventions established:** Fresh prompt rendering remains the default (`resume=False`); downstream #050/#051 should opt into `resume=True` only after resume eligibility succeeds.
**Notes for next iteration:** #050/#051 must pass the resume flag from scheduler/adapter wiring and still handle `--skill` loading outside prompt rendering.

## #050 Pi RPC dispatch + resume end-to-end — 2026-06-13

**What changed:** Added `PiRpcAgentAdapter` with `pi --mode rpc` dispatch, derived session ids, JSONL event pumping, timeout aborts, and scheduler Session Resume wiring.
**Files:** `agent_runner.py`, `scheduler.py`, `config.py`, `main.py`, `plane_adapter.py`, `tracker_podium.py`, `prompt_renderer.py`, `tests/test_agent_runner.py`, `tests/test_dispatch_compaction.py`, `.kanban/issues/050-pi-resume-end-to-end.md`.
**Decisions:** Kept one-shot `PiAgentAdapter` as the default rollback path; bindings opt into RPC with `pi_mode: rpc`. Resume runs skip Podium context compaction and render only the newest operator reply; predicate/runtime failures fall back to fresh full re-feed in the same tick.
**Conventions established:** Pi RPC run rows record `agent_session_sha` and `resumed`; the final assistant text still flows through `AgentResult.stdout` so result/summary parsing remains adapter-neutral.
**Notes for next iteration:** #051 can mirror the resume/fallback flow for Claude; #056/#058 should build steering/lifecycle on the RPC event pump without changing the one-shot rollback path.

## #051 Claude resume end-to-end — 2026-06-13

**What changed:** Extended Claude tmux dispatch to launch fresh sessions with `--session-id <derived>` and resumed sessions with `--resume <derived>`, while scheduler resume eligibility now covers Claude as well as Pi RPC.
**Files:** `claude_runner.py`, `scheduler.py`, `tests/test_claude_runner.py`, `tests/test_dispatch_compaction.py`, `.kanban/issues/051-claude-resume-end-to-end.md`.
**Decisions:** Kept the existing scheduler fallback path shared across agents: a Claude resume exception or non-zero result records a failed resumed Run, logs `resume_failed ... fell_back=true`, then starts a fresh full re-feed Run in the same tick.
**Conventions established:** Claude resume uses the same `derive_session_id`, `evaluate_resume_eligibility`, delta-only prompt rendering, compaction-skip, and run-row `agent_session_sha`/`resumed` fields as Pi RPC.
**Notes for next iteration:** #052 can rely on both Pi RPC and Claude preserving parked question context through operator reply resume; #053 can resolve Claude session files with the existing #048 path helper.

## #052 Question Park — 2026-06-13

**What changed:** Added a `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END` output outcome that parks an agent question to `in_review`, records the question as a comment, and leaves blocked-on-error behavior unchanged.
**Files:** `prompt_renderer.py`, `scheduler.py`, `claude_runner.py`, `tests/test_prompt_renderer.py`, `tests/test_prompt_renderer_podium.py`, `tests/test_scheduler.py`, `tests/test_claude_runner.py`, `.kanban/issues/052-question-park.md`.
**Decisions:** Implemented Question Park as a scheduler verdict/comment/state mapping, not a new state machine; operator replies continue to use the existing `in_review` redispatch and #050/#051 resume path.
**Conventions established:** Agents must use `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END` instead of interactive questions when they need operator clarification.
**Notes for next iteration:** #055 can build checkpointed exploration on this park-and-reply behavior; #056 remains separate live steering for Pi RPC.

## #053 Live Session Tail — 2026-06-13

**What changed:** Added an API-process session tailer that reads running issue session JSONL files and publishes appended lines as `run.tail` WebSocket events; added a Session flyout tab that renders tail lines live.
**Files:** `web/api/main.py`, `web/api/tests/test_session_tail.py`, `web/frontend/components/IssueFlyout.tsx`, `web/frontend/components/QueryProvider.tsx`, `web/frontend/components/SessionTailPanel.tsx`, `web/frontend/playwright.config.ts`, `web/frontend/tests/fixtures.ts`, `web/frontend/tests/session-tail.spec.ts`, `.kanban/issues/053-live-session-tail.md`.
**Decisions:** Kept live tail entirely in the web/API process and left the scheduler process model unchanged per ADR-0006. Tail reads are byte-range `rb` reads only; absent/empty/locked files degrade to no event and an empty panel.
**Conventions established:** `run.tail` WebSocket payloads use `{ type: "run.tail", issue_id, lines }`; frontend tail rendering consumes the shared `QueryProvider` WebSocket connection and filters by issue id.
**Notes for next iteration:** #057 can build a richer tail/steer UI on the Session tab; #056 remains the pi RPC steering channel and does not need to replace JSONL tailing.

## #054 Fast re-dispatch on operator reply — 2026-06-13

**What changed:** Added a cross-process wake sentinel for operator reply re-dispatch and made the scheduler break out of poll sleeps within one short interval.
**Files:** `web/api/wake_signal.py`, `web/api/main.py`, `scheduler.py`, `web/api/tests/test_reply.py`, `tests/test_scheduler.py`, `.kanban/issues/054-fast-redispatch-on-reply.md`.
**Decisions:** Used a filesystem sentinel (`SYMPHONY_WAKE_SENTINEL_PATH`, else `SYMPHONY_RUNTIME_DIR/reply-wake`, else `/tmp/symphony/reply-wake`) instead of an API push path, preserving ADR-0006 separate-process boundaries.
**Conventions established:** Any successful API-side action that flips an issue back to `todo` for scheduler re-dispatch should touch the wake sentinel after the durable DB commit.
**Notes for next iteration:** #056/#057 steering can rely on faster between-run reply pickup; this does not add live mid-run steering.
