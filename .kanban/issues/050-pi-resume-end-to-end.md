---
id: 050
title: Pi RPC dispatch + resume end-to-end (Slice A)
status: in-progress
blocked_by: [047, 048, 049]
parent: null
priority: 0
created: 2026-06-13
updated: 2026-06-13
actor: ralph
---

## What to build

**Re-sequenced onto RPC by ADR-0010** (was: `pi --print --session-id`). Build the pi RPC dispatch adapter and wire Session Resume continuity through it, delivering both RPC run-to-completion parity (Slice A) and the in_review/blocked → operator-reply → re-dispatch resume loop on one mechanism.

New `PiRpcAgentAdapter` (alongside the existing `PiAgentAdapter`, which stays as the proven one-shot fallback/rollback). The adapter spawns `pi --mode rpc` and runs an internal event-pump loop instead of `process.communicate()`:

- Launch `pi --mode rpc --provider <p> --model <m> [--skill <dir>] --session-id <derive_session_id(issue.id)>` from the bound repo cwd. NOT `--no-session` (the session must persist for resume + #053 tail), NOT `--continue` (silent-fresh hazard). Each Run is a fresh process that resumes the persisted session by id, so `--skill <dir>` is re-passed at launch on **resume** runs too: when an operator reply names a new `preferred_skill`, that skill's dir is loaded on the resume launch and #049 prepends its invoke directive. A skill-less reply resumes with no `--skill`.
- Send the rendered prompt as `{"type":"prompt","message":...}` on stdin; pump JSONL events from stdout until `agent_end`.
- Map to the existing `AgentResult`: `stdout` = the final assistant text (carrying the `SYMPHONY_RESULT`/`SYMPHONY_SUMMARY` lines), so the scheduler verdict/summary/metrics scrape (`scheduler.py:233`) is unchanged. `agent_end` → exit 0; a stream `error`/process death → non-zero; wall-clock `run_timeout_ms` exceeded → send `{"type":"abort"}`, then `timed_out=True`.
- Resume vs fresh by the #048 eligibility predicate: on `resume`, render the delta-only prompt (#049), set `resumed=true`, record `agent_session_sha`. On `refeed` or a runtime resume error, fall back within the same tick to a fresh session + full re-feed (`resume_skipped`/`resume_failed ... fell_back=true` markers). Skip `_maybe_compact_context` on resume runs.
- **Session window on a long resume loop (grill-me 2026-06-13, C-0179):** because `_maybe_compact_context` is skipped on resume, the RPC *session* — not #026 — owns its own context window across a long reply loop. Rely on pi's native auto-compaction (`set_auto_compaction`/`compact`); confirm it is on by default under the service env in the spike, and enable it explicitly if not. The two stores are orthogonal: #026 still compacts `context_md` on fresh/fallback dispatches, the native session self-compacts — neither reconciles with the other.

Selection: a per-binding flag (e.g. `pi_mode: rpc`) routes a binding's pi dispatch to the RPC adapter; bindings without it keep one-shot `--print`. Test first on a throwaway binding; do not flip `homelab`/`trading`/`symphony` until soaked.

Scope guard: resume only in the in_review/blocked reply loop; Done-reopen falls back to re-feed; worktree lifecycle (#021) untouched. Steering, live tail fan-out, and the steer channel are NOT in this slice (see #056/#053/#058).

Parity verified 2026-06-13 (ADR-0010 spike): `pi --mode rpc` honors `--skill`, CLAUDE.md context, provider/model; streams `message_update` deltas; completes deterministically on `agent_end`.

## Acceptance criteria

- [ ] `PiRpcAgentAdapter` dispatches `pi --mode rpc` with `--session-id <derived>`, never `--no-session`/`--continue`, and returns an `AgentResult` whose `stdout` is the final assistant text.
- [ ] Run-to-completion parity: a normal run completes on `agent_end` exit 0; verdict/summary/metrics parse identically to the one-shot path; timeout sends `abort` and returns `timed_out=True`.
- [ ] Resume run renders the delta-only prompt (#049); fallback renders full re-feed; `resumed`/`agent_session_sha` recorded for both paths.
- [ ] Predicate failure and a simulated resume/runtime error fall back to fresh+re-feed in the same tick with the documented markers.
- [ ] `_maybe_compact_context` is NOT invoked on resume runs and IS on fresh/fallback runs.
- [ ] One-shot `PiAgentAdapter` remains intact and selectable (rollback path); a per-binding flag selects RPC vs one-shot.
- [ ] Tests fake the RPC subprocess stdio with scripted JSONL events (existing injected-fake style).

## Verification

`uv run pytest tests/test_dispatch_compaction.py tests/test_scheduler*.py tests/test_session_continuity.py tests/test_agent_runner*.py -q`

## Blocked by

- Blocked by #047, #048, #049
