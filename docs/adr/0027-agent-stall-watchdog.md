---
status: accepted
---

# ADR-0027 — Agent stall watchdog: abort frozen agents on RPC-event silence

## Context

ADR-0026 retries *terminated* agents (nonzero exit / `timed_out`) classified by stderr signature. It does not cover a **frozen** agent: a live `pi` process producing no output, stuck mid-context-compaction (`WCHAN=ep_poll`, 0% CPU). Such an agent holds its `locks` resource and the run until the 2h `run_timeout_ms` hard timeout (`config.py:175`). Observed on #136 review run #417 — frozen ~50 min, killed manually to exit 143 (C-0336).

**Production dispatch path (corrected by dev-review, 2026-06-25).** The original C-0336 framing pinned the stall on `agent_runner.py:406` `process.communicate(timeout=...)`. That is the **one-shot** path, and **no binding uses it** — every binding in `bindings.yml` is `pi_mode: rpc` (homelab, symphony, dotfiles, n8n, ai-web-chat). The live path is `run_pi_rpc_agent` → **`_drain_rpc_events`** (`agent_runner.py:1177`), a `while True` loop that reads pi's JSONL event stream line-by-line on a 0.5s poll (`RPC_STEER_POLL_INTERVAL_SECONDS`) until `agent_end`, error, EOF, or `deadline = started + run_timeout_ms/1000` (the 2h ceiling). So the watchdog must live in *that* loop, and a live event stream is already available as a liveness signal.

## Decision

Add a **stall watchdog** to the existing `_drain_rpc_events` loop that aborts a run after N minutes of RPC-event silence, independent of the 2h hard deadline.

1. **Liveness signal = any RPC event line arriving.** The drain loop already calls `read_line()` every poll; track the wall-clock time of the last non-empty line. Silence = no JSONL event (assistant delta, thinking delta, tool lifecycle, `message_update`/`message_end`, status) for N minutes. This is strictly richer than session-jsonl mtime (which only flushes at turn boundaries) and — unlike mtime — works uniformly for **local and remote** RPC, since remote events flow back over SSH stdout into the same loop. Rejected alternatives: **session-jsonl mtime** (the original proposal — unusable for remote dispatch, where the file is on the remote host the orchestrator cannot stat; also coarser than the event stream); **stdout bytes via `communicate()`** (that path is unused in production). The watchdog bounds *maximum silence*; it cannot distinguish a slow-but-alive operation from a true freeze, so N must sit above the longest legitimate silent interval.

2. **Watchdog lives in the `_drain_rpc_events` loop — no `communicate()` surgery.** The loop already owns the process handle and already performs the abort-and-kill on its 2h deadline branch (`_send_rpc_abort` + `_terminate_process_group`). Add a *second, shorter* silence deadline: when `now - last_event_time > stall_timeout`, take the **same** abort+kill path the timeout branch uses and return a `_DrainResult` flagged as a stall. `reconcile_stale_running` stays unchanged as the crash-recovery backstop. (Pre-existing, out of scope: that sweep transitions tracker state but does not SIGKILL a lingering process — tracked as a separate follow-up.)

3. **Stall is a new retry class, not a transient.** A stall abort has *no stderr signature* (we killed it precisely because it was silent), so it cannot ride ADR-0026's signature allowlist. The synthesized `AgentResult` carries an explicit watchdog **sentinel** — not a faked stderr string (a fake would be a lie the contract-gate corpus would later trip over). `_classify_terminal` routes the sentinel to a distinct retry class with its own `### Symphony Retry (stall · N)` marker. Rationale: ADR-0026 transients are provider-side, self-identified, and likely to succeed on retry; a freeze is a local liveness failure of unknown cause likely to recur identically (same model, same compaction point). Conflating their budgets would let a chronic freezer burn the transient budget and mask a real bug as a flaky provider.

4. **Reuses `verdict="retry"`; stall cap = 1; counted by a stall-aware counter.** No new verdict — migration 0012's `retry` already covers it. The stall cap is 1 (vs 2 for overload/5xx): a freeze is more likely deterministic than a 503, mirroring how ADR-0026 caps timeouts lower than overloads. **`count_retries()` (`redispatch_core.py:40`) only matches `RETRY_MARKER_PREFIX = "### Symphony Retry (transient"` and will not see a `(stall · N)` marker** — so the implementation needs a stall-aware counter. The stall cap and the transient cap are **separate** (the whole point of a distinct class is distinct budgets/diagnostics), but to prevent an indefinite `stall → transient → stall` ping-pong that never blocks, a **combined retry ceiling** caps total retries of any kind per issue. Separate per-class caps for shape; one combined ceiling for liveness.

5. **N = single global `stall_timeout_ms`, default 15 min.** N is gated by the longest legitimate *silent interval* — a long context-compaction (the observed freeze cause, model-internal and silent) or a long single tool call that emits no intermediate events — not total provider latency, so it is **not** sharded per-provider. 15 min sits above any plausible silent interval, below the ~50 min manual-kill tolerance and the 2h ceiling. A long-but-alive tool call (e.g. a 16-min `npm install` with no intermediate events) is the known false-positive risk; per-provider or per-phase N is deferred until logs show a false-positive stall-abort.

## Consequences

- The fix is contained to the existing `_drain_rpc_events` loop (add a silence deadline + reuse its abort path) — much smaller than the originally-scoped `communicate()` rewrite, because the production path already polls.
- A new marker family `### Symphony Retry (stall · N)` joins `(transient · N)`; a stall-aware counter and a combined retry ceiling are required.
- A frozen agent frees its lock in ~15 min instead of 2h, on both local and remote RPC.
- A false-positive stall-abort (killing a slow-but-alive agent during a silent tool call) is possible and is the explicit signal to raise N or shard it.
