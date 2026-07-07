---
title: "ADR-0034 — Carrier-disruption persistence: pi in-process budget + Symphony stall routing for pi-retry tags"
type: analysis
status: promoted
created: 2026-07-06
updated: 2026-07-06
sources:
  - docs/adr/0034-carrier-disruption-persistence-two-layers.md
  - redispatch_core.py
  - scheduler/__init__.py
  - scheduler/transient_retry.py
  - ~/.pi/agent/settings.json
  - /home/james/dotfiles/.pi/agent/extensions/pi-retry/src/retry.ts
  - tests/test_scheduler.py
  - tests/test_transient_retry.py
confidence: high
tags: [adr, carrier-disruption, stall, retry, pi-retry, provider-stall, two-detector-gap, load-bearing-contract]
---

# ADR-0034 — Carrier-disruption persistence: two layers

ADR-0034 (`accepted` 2026-07-06, after grill-me on pi-rmm issue #295 / run #1117) makes
carrier-disruption persistence live at **two layers** deliberately. It finishes ADR-0027's
half-built stall path rather than adding a parallel detector [source: docs/adr/0034-carrier-disruption-persistence-two-layers.md].

## The two-detector gap (the "why")

A provider stream can stall two different ways, and Symphony had a gap between its two
detectors that neither covered:

- **ADR-0027 stall** — `agent_runner._drain_rpc_events` detects *pi itself* freezing (the
  RPC event stream goes silent, 0% CPU). It injects the `SYMPHONY_STALL_WATCHDOG` sentinel
  into stderr, which `_maybe_retry_stall` gates on → stall-retry path. (See [ADR-0026
  transient-failure retry](/analyses/adr-0026-transient-failure-retry.md) for the stall
  follow-up; ADR-0027 has no analysis page of its own — only `docs/adr/0027`.)
- **pi-retry extension** (`dotfiles/.pi/agent/extensions/pi-retry`) — detects the
  *provider's* stream stalling **while pi keeps narrating** (stdout keeps flowing, so the
  RPC stream is never silent and ADR-0027 never trips). It aborts the provider request and
  tags the final error with one of four stable literals, plus the injected hint
  `provider returned error`, which makes pi's built-in auto-retry pick it up and retry
  **in-process** [source: /home/james/dotfiles/.pi/agent/extensions/pi-retry/src/retry.ts].

Run #1117 hit the second case: ZAI stopped sending tokens, pi kept emitting stdout
narration, so `drain.stalled` never set, `SYMPHONY_STALL_WATCHDOG` was never injected,
`_maybe_retry_stall` returned `None`, and `is_transient`'s regex matched none of the tag
text → fell through to `exit_code != 0 → block`. pi had already exhausted its 4 in-process
attempts over ~12 min; the run blocked despite being purely carrier-transient.

This gap is distinct from C-0336 (the original "no stall detection at all" gap that
ADR-0027 closed for the pi-freeze case): C-0336 was "no detector"; ADR-0034's gap is
"ADR-0027's detector only sees pi-freeze, not provider-stall-while-pi-narrates."

## Decision: two layers

1. **pi in-process retry budget** — `~/.pi/agent/settings.json` `retry.maxRetries` raised
   3 → 6 (host-global; `baseDelayMs` stays at pi's default 2000, `provider.timeoutMs`
   already 600000). Rides out short carrier blips **inside one run** via pi's
   `_isRetryableError` classifier (which correctly excludes context-overflow, quota,
   billing). Affects interactive pi too — desirable [source: ~/.pi/agent/settings.json;
   pi core `dist/core/settings-manager.js` maxRetries default 3, baseDelayMs default 2000].

2. **Symphony stall routing for the pi-retry tags** — broaden `_maybe_retry_stall`'s gate
   (`scheduler/__init__.py`) from `SYMPHONY_STALL_WATCHDOG only` to **sentinel OR any of
   the four tag literals**, and raise `MAX_STALL_RETRIES` (`redispatch_core.py`) 1 → 3.
   The RPC sentinel (ADR-0027) stays an alternative trigger, unchanged.

## The load-bearing contract: four-tag closed allowlist

`PI_RETRY_TAGS` (`redispatch_core.py`) is a `frozenset` of exactly these four stable
literals, owned by the dotfiles `pi-retry` extension:

- `[stall-watchdog-retry]`
- `[rate-limit-retry]`
- `[unknown-error-retry]`
- `[codex-websocket-limit-retry]`

The gate matches these literals in stderr (not a regex of provider wording, which drifts).
A genuine crash / OOM / bad-key / config error carries none of them and still blocks,
preserving the "never loop a real bug" guarantee from ADR-0026. **Renaming a tag in the
extension without updating `PI_RETRY_TAGS` silently regresses carrier-disruption exits to
block** (fail-closed, not silent-loop). If the extension ever adds a 5th tag, the Symphony
gate must be updated in lockstep. This is the most load-bearing fact in the whole change —
see C-0362 [source: redispatch_core.py; retry.ts; tests/test_transient_retry.py pins the
set to exactly the four literals].

## Why the stall path, not the transient path

`_classify_terminal` (`scheduler/__init__.py`) runs the handlers in order **stall →
transient → block**. The stall handler runs *first*, so matching the tags there means they
never reach `is_transient`. The tags are therefore **not** added to `is_transient` (that
would be dead code). Routing to stall rather than transient is also load-bearing: the stall
cap (3, after this change) gives the carrier-persistence budget the operator asked for, vs
the transient cap (2). All four tags route through the one stall path — the operator model
treats every carrier disruption as a single persistence class, so the three non-stall tags
deliberately share the stall path even though they are provider-side rather than
freeze-side. See C-0364.

## The "don't re-dispatch while pi is mid-retry" property

The pi-retry tags only reach Symphony's stderr **after** pi's in-process auto-retry has
exhausted: the extension's injected `provider returned error` hint triggers pi's *native*
retry loop, and only when that loop gives up does pi exit 1 with the tagged stderr. So
Symphony-level re-dispatch never fires while pi is still retrying — layer 2 is strictly a
backstop behind layer 1.

## Shared combined budget shadows the stall cap

`MAX_COMBINED_RETRIES = 3` stays the authoritative ceiling across stall + transient +
timeout (`redispatch_core.py`). Raising `MAX_STALL_RETRIES` to 3 gives full persistence
headroom *only* when no transient retry has already been spent on the same issue; a stall +
transient mix still hard-blocks at a combined 3.

A subtle consequence: because `MAX_STALL_RETRIES` now **equals** `MAX_COMBINED_RETRIES`
(both 3), the combined-ceiling check (`count_all_retries(comments_md) >=
MAX_COMBINED_RETRIES`) runs in `_classify_terminal` *before* `_maybe_retry_stall`, so it
shadows the stall-exhausted branch — a 4th consecutive stall exits with reason
`combined-ceiling-exhausted`, not `stall-retry-exhausted-*`. This is the ADR's documented
"firm combined ceiling matters more than any single class's budget." See C-0365.

## Implementation (two code edits + one config edit)

- `redispatch_core.py`: added `PI_RETRY_TAGS` frozenset; `MAX_STALL_RETRIES 1 → 3`
  (`MAX_COMBINED_RETRIES` unchanged at 3).
- `scheduler/transient_retry.py`: re-exports `PI_RETRY_TAGS` from `redispatch_core`
  (the scheduler imports stall-retry vocabulary through this bridge; `redispatch_core` is
  the source of truth).
- `scheduler/__init__.py` `_maybe_retry_stall`: gate broadened from
  `STALL_WATCHDOG_SENTINEL not in stderr` to
  `sentinel not in stderr AND not any(tag in stderr for tag in PI_RETRY_TAGS)`.
- `~/.pi/agent/settings.json`: `retry.maxRetries: 6`.

Deploy = `symphony-host.service` restart (scheduler code, not `podium-api`). Lever 1 (pi
config) needs no deploy — read at pi startup, takes effect on next dispatch.

## Tests

- `tests/test_scheduler.py`: parametrized over all four tags — a tagged-stderr exit with no
  RPC sentinel routes to `stall-retry-implement` with a `(stall · 1)` marker and requeues
  to `todo`; 2nd + 3rd stall now requeue under the raised cap; 4th stall blocks at the
  **combined** ceiling (`combined-ceiling-exhausted`); an untagged non-transient crash
  (e.g. `invalid API key (401)`) still blocks with reason `nonzero` (fail-closed).
- `tests/test_transient_retry.py`: `MAX_STALL_RETRIES == 3`; `PI_RETRY_TAGS` pinned to
  exactly the four documented literals.
- The ADR-0029 frozen contract-gate corpus (`tests/test_contract_gate.py`) still passes.

## Claims

- C-0362 — the four-tag `PI_RETRY_TAGS` closed-allowlist contract (Symphony ↔ dotfiles
  pi-retry).
- C-0363 — ADR-0034 decision (two layers; amends C-0337/ADR-0027's boundary).
- C-0364 — `_classify_terminal` stall→transient→block ordering makes the tags
  is_transient-dead-code.
- C-0365 — `MAX_STALL_RETRIES == MAX_COMBINED_RETRIES == 3` shadows the stall-exhausted
  branch.

# Citations

- `docs/adr/0034-carrier-disruption-persistence-two-layers.md` — the accepted ADR (canonical record).
- `redispatch_core.py` — `PI_RETRY_TAGS`, `MAX_STALL_RETRIES`, `MAX_COMBINED_RETRIES`.
- `scheduler/__init__.py` — `_maybe_retry_stall` gate, `_classify_terminal` handler order.
- `scheduler/transient_retry.py` — `PI_RETRY_TAGS` re-export, `is_transient` allowlist.
- `/home/james/dotfiles/.pi/agent/extensions/pi-retry/src/retry.ts` — the four tag literals + `provider returned error` hint.
- `~/.pi/agent/settings.json` — `retry.maxRetries: 6`.
- `tests/test_scheduler.py`, `tests/test_transient_retry.py` — gate-routing + cap tests.
- `docs/adr/0026-transient-failure-retry-not-block.md`, `docs/adr/0027-agent-stall-watchdog.md` — the two detectors ADR-0034 bridges.
