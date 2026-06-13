---
id: 050
title: Pi RPC dispatch + resume end-to-end (Slice A)
status: done
blocked_by: [047, 048, 049]
parent: null
priority: 0
created: 2026-06-13
updated: 2026-06-13
actor: ralph
---

## FIXED 2026-06-13 — both defects resolved, Slice A re-verified in-app (PASS)

The two reopen defects below are fixed in `agent_runner.py`:

1. **Reader rewritten** (`_rpc_line_reader` replaces `_read_rpc_line`). It reads the raw fd via `os.read` (not the buffered TextIO wrapper) and **drains every buffered line before polling the fd again**, so the terminal `agent_end` is never stranded when pi goes idle. A no-`fileno` stream (the `io.StringIO` test fake) falls back to synchronous `readline`. Completion is detected from `agent_end`; EOF only ends the loop for a process that exits on its own.
2. **Text extraction tightened** (`_assistant_delta` replaces `_event_text`/`_stringify_event_text`/`_rpc_text_from_raw`). Only `message_update` → `assistantMessageEvent.type=="text_delta"` → `.delta` is captured (plus the simplified top-level `delta` the fakes use); thinking/tool-call deltas and every non-`message_update` event (extension `setStatus`/`notify` banners, prompt echoes) are excluded, so the `SYMPHONY_RESULT`/`SYMPHONY_SUMMARY` scrape is clean.

Verification (real pi 0.78.1, `openai-codex`/`gpt-5.4-mini`): `run_pi_rpc_agent` completed in **~15s** (was 120s timeout), `timed_out=False`, `exit=0`, `stdout=='PARITY_OK'`; a second call on the same derived session-id + cwd resumed across processes and recalled the token (`OVERALL=PASS`). Added `tests/test_agent_runner.py::test_run_pi_rpc_agent_extracts_only_assistant_text_deltas` (real event shape + exclusion) and an env-gated `test_run_pi_rpc_agent_real_pi_completion_parity` (set `SYMPHONY_RPC_PARITY=1`).

Still TODO before enabling on real bindings / accepting ADR-0010: a **throwaway-binding soak** through the full scheduler→adapter→verdict path (this fix was verified at the adapter level, not yet a full Podium binding dispatch). Do not set `pi_mode: rpc` on `homelab`/`trading`/`symphony` until that soak passes.

## (historical) REOPENED 2026-06-13 — failed in-app Slice A verification (ADR-0010 gate)

The merged adapter passes its faked-stdio unit tests but **hangs to timeout on every real `pi --mode rpc` dispatch.** Verified by driving the real adapter (`run_pi_rpc_agent`) against pi 0.78.1 in a throwaway cwd: both a fresh call and a resume call returned `timed_out=True` at the full `run_timeout_ms`, though the model completed and the session resumed (call 2 recalled call 1's token). A protocol-compliant blocking reader saw `agent_end` in **9.7s** for the same prompt, so pi is fine — the adapter is broken. Two defects to fix:

1. **Completion never detected (blocking).** `_read_rpc_line` (`agent_runner.py:552`) registers a `selectors` watch on the **raw fd** then calls `stdout.readline()` on the **buffered** TextIO stream. pi RPC writes its event burst then stays alive idle (persistent session server — no process exit, no stdout EOF; `process_alive_after_agent_end=True` confirmed). The final `agent_end` line sits in the TextIOWrapper buffer while the selector polls the now-empty fd → never ready → `readline()` never runs → the loop spins to the deadline. Fix: read with a protocol-compliant LF-split reader (e.g. iterate `proc.stdout`, or read the raw fd with our own buffer per `docs/rpc.md` framing notes), and enforce `run_timeout_ms` via a reader-thread + deadline (or non-blocking raw read), NOT selector-on-fd + buffered readline.

2. **Assistant text polluted.** `_event_text`/`_stringify_event_text` scrape `message`/`content`/`text` across all event types, capturing fire-and-forget `setStatus`/`notify` extension banners (e.g. "Advisor restored…"), the echoed prompt, and cumulative `message_update` partials → garbage like `PARPARITYPARITY_OK…`. This would corrupt the `SYMPHONY_RESULT`/`SYMPHONY_SUMMARY` scrape. Fix: extract assistant text only from `message_update` → `assistantMessageEvent.type=="text_delta"` → `.delta` (concatenated), or from the final `agent_end`/`message_end` assistant message; ignore `extension_ui_request` and other event types.

Add a real (non-faked) parity test gated behind an env flag / skipif so CI stays hermetic but the parity path is exercisable. Do NOT flip ADR-0010 to `accepted` and do NOT enable `pi_mode: rpc` on any binding until both defects are fixed and re-verified in-app. The broken adapter is currently dormant (no binding sets `pi_mode: rpc`; one-shot `PiAgentAdapter` remains the live default), so nothing in production is affected.

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

- [x] `PiRpcAgentAdapter` dispatches `pi --mode rpc` with `--session-id <derived>`, never `--no-session`/`--continue`, and returns an `AgentResult` whose `stdout` is the final assistant text.
- [x] Run-to-completion parity: a normal run completes on `agent_end` exit 0; verdict/summary/metrics parse identically to the one-shot path; timeout sends `abort` and returns `timed_out=True`.
- [x] Resume run renders the delta-only prompt (#049); fallback renders full re-feed; `resumed`/`agent_session_sha` recorded for both paths.
- [x] Predicate failure and a simulated resume/runtime error fall back to fresh+re-feed in the same tick with the documented markers.
- [x] `_maybe_compact_context` is NOT invoked on resume runs and IS on fresh/fallback runs.
- [x] One-shot `PiAgentAdapter` remains intact and selectable (rollback path); a per-binding flag selects RPC vs one-shot.
- [x] Tests fake the RPC subprocess stdio with scripted JSONL events (existing injected-fake style).

## Verification

`uv run pytest tests/test_dispatch_compaction.py tests/test_scheduler*.py tests/test_session_continuity.py tests/test_agent_runner*.py -q`

## Blocked by

- Blocked by #047, #048, #049

## Implementation Notes

Implemented `PiRpcAgentAdapter` and `run_pi_rpc_agent` for `pi --mode rpc` dispatch with derived session ids, JSONL event pumping, abort-on-timeout, and final assistant text mapped into `AgentResult.stdout`. Added per-binding `pi_mode: rpc` routing while preserving the one-shot `PiAgentAdapter` rollback path. Wired scheduler resume eligibility, delta-only prompt rendering, resume/fallback run-row fields, runtime fallback, and compaction skipping on resume. Added regression coverage for RPC stdio, timeout abort, and resume prompt/run-row behavior.
