---
status: accepted
---

# ADR-0029 — Contract gate scores parser coverage over a frozen corpus, not the live DB

## Context

`contract_gate.py` enforces that Symphony's terminal-marker parser keeps extracting the right signal from run logs. It does two things:

- **`check_locked`** pins specific runs (30, 39, 120) to their parsed signal — a true regression guard against a marker-regex tightening that re-hides a signal.
- **`score` + a ratcheted baseline floor** computes coverage = fraction of exit-0 runs whose log carries a parseable marker, and fails if it drops below `contract_gate_baseline.json` (0.9314).

`score` reads the **live, growing `podium.db`** (`load_corpus`, `contract_gate.py:53,81`). As production runs accrete — including the empty/killed-mid-stream logs from today's flaky and watchdog-killed runs — coverage drifted 0.9314 → 0.9129, and `test_gate_passes_at_head` (`tests/test_contract_gate.py:18`) is red on `main`. This is **not** caused by any code change (not the deepseek switch, not ADR-0026).

The diagnosis: the coverage metric claims to measure **parser health** but is computed over a moving population, so it actually drops as **DB hygiene** degrades. The largest contributor is exit-0 runs with empty logs that carry no marker *because the run produced none* (killed mid-stream), not because the parser is broken — so the parser is correctly returning `None`, yet coverage falls. (Dev-review, 2026-06-25: empty/killed logs are not the *only* contributor — some runs carry a `SYMPHONY_RESULT` marker mid-line, e.g. `...knowledge.SYMPHONY_RESULT: done`, which the `^`-anchored `_RESULT_MARKER_RE` (`scheduler/markers.py:14`) correctly rejects. That is a parser-format boundary, not DB hygiene; it does not change the decision — those cases were never covered — but the drift is a mix, not purely empty logs.) The gate goes red for a reason unrelated to parser quality, becomes noise, and the only quick relief (`--update-baseline`) *locks in* the drift and defeats the ratchet.

## Decision

**Freeze the scoring corpus to a checked-in fixture; the gate no longer reads the live DB.**

- Coverage is measured over a pinned, reviewable set of run logs committed to the repo. It changes only when the *parser* changes or the *fixture* changes — never when production runs accrete.
- `check_locked` continues to pin its cases; the locked runs become a subset of the frozen fixture.
- **Seed** the fixture from the honest pre-drift corpus — the exit-0 runs the baseline was set against (175 runs / 0.9314), minus the post-drift garbage. This makes `test_gate_passes_at_head` green again *correctly* (the parser still covers the same real signals), not by lowering the bar. The fixture **must include runs 30, 39, and 120** or `check_locked` reports them missing (they are real pre-drift-era runs, so seeding from the n=175 corpus includes them). A future fixture update should also add a deliberate **mid-line-marker** example so a later relaxation of the `^` anchor registers as a coverage *gain*, not a silent no-op.
- **Leave the baseline number untouched** (0.9314). The frozen corpus reproduces ≥ baseline, so no baseline edit is needed and the drift is never locked in.

## Considered alternatives

- **Update the baseline.** Rejected as primary fix — the "learn to ignore the gate" path; accepts a lower floor to paper over a data problem and must be repeated as the DB accretes more empty logs.
- **Improve the parser for empty-log rows.** Rejected — a misdiagnosis. The parser is correct to return `None` on an empty/killed log; "covering" these means inventing a signal that isn't there.

## Rejected sibling issue: `markers.py` "retry gap"

The handoff flagged `scheduler/markers.py:14` (`SYMPHONY_RESULT: (done|review|blocked)`) as missing `retry`. **Rejected by design.** `_RESULT_MARKER_RE` parses the verdict an **agent** self-declares; `retry` is never an agent decision — both `verdict="retry"` writes are made by the orchestrator's `_finish_run_record` (`scheduler/__init__.py:1936,2027`) on **failed** runs, and the value goes straight to the `run.verdict` column (allowed by migration 0012). It never round-trips through `_parse_result_marker`. Adding `retry` to the regex would let an agent self-assign a retry and bypass the cap/cooldown/allowlist machinery — opening a hole, not closing a gap. The boundary is intentional: agents declare done/review/blocked; the machine declares retry.

## Consequences

- The gate stops reading `podium.db`; `load_corpus` reads the frozen fixture instead. `test_gate_passes_at_head` is no longer hostage to live-DB state.
- New terminal-signal shapes that appear in production do **not** enter the gate automatically — adding a case to the fixture becomes a deliberate, reviewed act (like adding a test). This is the intended discipline; the old automatic corpus growth is exactly what introduced the unreviewed drift.
- The gate now measures one thing honestly: parser coverage over a fixed, reviewable corpus.
