---
status: accepted
relates-to: ADR-0026 (transient-failure retry — the `is_transient` allowlist path this does NOT touch), ADR-0027 (agent stall watchdog — the stall-retry path this broadens and whose "stall = local liveness freeze" boundary this deliberately amends)
decided-with: James, 2026-07-06 (grill-me after pi-rmm issue #295 / run #1117 blocked on a ZAI `glm-5.2:high` provider-stream stall)
---

# Carrier-disruption persistence: two layers (pi in-process budget + Symphony stall routing for pi-retry tags)

## Context

A provider stream can stall two different ways, and Symphony had a gap between its
two detectors that neither covered:

- **ADR-0027 stall** — `agent_runner._drain_rpc_events` detects *pi itself*
  freezing (RPC event stream silent, 0% CPU). It injects the `SYMPHONY_STALL_WATCHDOG`
  sentinel into stderr, which `_maybe_retry_stall` gates on → stall-retry path (cap 1).
- **pi-retry extension** (`dotfiles/.pi/agent/extensions/pi-retry`) — detects the
  *provider's* stream stalling **while pi keeps narrating** (stdout flows, so the RPC
  stream is never silent and ADR-0027 never trips). It aborts the provider request and
  tags the final error with one of four stable literals — `[stall-watchdog-retry]`,
  `[rate-limit-retry]`, `[unknown-error-retry]`, `[codex-websocket-limit-retry]` — plus
  the injected hint `provider returned error`, which makes pi's built-in auto-retry
  pick it up and retry **in-process**.

Issue #295 / run #1117 hit the second case: ZAI stopped sending tokens, pi kept
emitting stdout narration ("Now reading the SPEC…"), so `drain.stalled` never set,
`SYMPHONY_STALL_WATCHDOG` was never injected, `_maybe_retry_stall` returned `None`,
and `is_transient`'s regex matched none of the tag text → fell through to the
`exit_code != 0 → block` path. pi had already exhausted its 4 in-process attempts
over ~12 min; the run blocked despite being purely carrier-transient.

The stall machinery (`MAX_STALL_RETRIES`, `format_stall_retry_marker`,
`count_stall_retries`, the stall/review-stall handler branches) was already built by
ADR-0027 — it just never fired for provider stalls because its gate only knew the RPC
sentinel.

## Decision

Persistence against carrier disruption lives at **two layers**, deliberately:

1. **pi in-process retry budget** — raise `~/.pi/agent/settings.json`
   `retry.maxRetries` 3 → 6 (keep `baseDelayMs` 2000, `provider.timeoutMs` 600000).
   Rides out short carrier blips **inside one run** via pi's already-trusted
   `_isRetryableError` classifier (which correctly excludes context-overflow, quota,
   and billing). Host-global setting; affects interactive pi too, which is desirable.

2. **Symphony stall routing for pi-retry tags** — broaden `_maybe_retry_stall`'s gate
   (`scheduler/__init__.py`) from `SYMPHONY_STALL_WATCHDOG only` to
   **sentinel OR any of the four pi-retry tag literals**, and raise
   `MAX_STALL_RETRIES` (`redispatch_core.py`) 1 → 3.

   This **finishes ADR-0027's half-built stall path** rather than adding a parallel
   detector: provider-tagged exhaustions now reach the existing stall-retry handler,
   get a `### Symphony Retry (stall · N)` marker, and requeue to `todo`/`in_review`
   with the existing combined-ceiling guard.

The four tags are treated as a **closed allowlist of stable literals owned by the
extension** — not a substring/regex of provider wording (which drifts). A genuine
crash / OOM / bad-key / config error carries none of these literals and still blocks,
preserving the "never loop a real bug" guarantee from ADR-0026.

### Why the stall path, not the transient path

`_classify_terminal` runs the handlers in order **stall → transient → block**. The
stall handler runs *first*, so matching the tags there means they never reach
`is_transient`. The tags are therefore **not** added to `is_transient` (that would be
dead code, since stall intercepts first). Routing to stall rather than transient is
also load-bearing: the stall cap (3, after this change) gives the carrier-persistence
budget the operator asked for, vs the transient cap (2). All four tags route through
the one stall path — the operator model treats every carrier disruption as a single
persistence class, so the three non-stall tags (`rate-limit`, `unknown-error`,
`codex-websocket`) deliberately share the stall path even though they are provider-side
rather than freeze-side.

### The "don't re-dispatch while pi is mid-retry" property

The pi-retry tags only reach Symphony's stderr **after** pi's in-process auto-retry has
exhausted: the extension's injected `provider returned error` hint triggers pi's
*native* retry loop, and only when that loop gives up does pi exit 1 with the tagged
stderr. So Symphony-level re-dispatch never fires while pi is still retrying — layer 2
is strictly a backstop behind layer 1, exactly the separation the operator wanted.

### Shared combined budget is intentional

`MAX_COMBINED_RETRIES = 3` stays the authoritative ceiling across stall + transient +
timeout. Raising `MAX_STALL_RETRIES` to 3 therefore gives full persistence headroom
*only* when no transient retry has already been spent on the same issue; a stall +
transient mix still hard-blocks at a combined 3. This is the intended behavior: the
firm ceiling matters more than any single class getting its full budget.

## Consequences

- A carrier stall like #295 self-heals (up to 3 stall re-dispatches, behind pi's 6
  in-process attempts) instead of blocking after one ~12-min run.
- Layer 1 (pi budget) is a host-global config edit; layer 2 (Symphony routing) is two
  edits — broaden one gate, bump one constant. No new module, marker, cap, or verdict.
- The four tag literals become a load-bearing contract between the dotfiles
  `pi-retry` extension and the Symphony classifier; renaming a tag in the extension
  without updating the gate silently regresses to block (fail-closed, not silent-loop).
- ADR-0027's "stall = local liveness freeze of unknown cause" boundary is deliberately
  widened to include provider-side exhaustion; the combined ceiling still prevents an
  indefinite stall↔transient ping-pong.
- Tests + the frozen contract-gate corpus (ADR-0029) must cover the broadened gate;
  existing stall tests assert the RPC-sentinel path, which is unchanged.

## Considered options

- **Add the four tags to `is_transient` instead of the stall gate** — rejected: the
  stall handler runs first, so the tags would never reach `is_transient` (dead code),
  and even if reordered, the transient cap (2) is lower than the carrier-persistence
  budget wanted.
- **Extend to pi's native `_isRetryableError` regex** (overloaded / 5xx / network) at
  the Symphony layer — rejected: re-introduces the provider-wording fragility the
  closed-literal allowlist exists to avoid; native-retryable exhaust without a tag is
  already handled by `is_transient` today.
- **Re-dispatch on any untagged exit-1** — rejected: sweeps in genuine crashes / OOM /
  bad-key / config errors with no carrier signal; the closed allowlist is what keeps
  the "never loop a real bug" guarantee.
- **A separate carrier-retry marker/class** — rejected: duplicates ADR-0027's stall
  machinery for no behavioral gain; reusing it is the ponytail choice.
