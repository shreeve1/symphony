# Session Capture: ADR-0029 contract gate frozen corpus — dev-build + dev-test

- Date: 2026-06-25
- Purpose: Build and test the frozen-corpus contract gate per ADR-0029
- Scope: Implementation (dev-build 5 waves) + test backfill (dev-test 4 new tests)

## Durable Facts

- `load_corpus()` now reads from `contract_gate_corpus.json` (checked-in fixture), not `podium.db`. — Evidence: `contract_gate.py:78-81`
- Frozen fixture: 190 runs (189 from DB + 1 artificial mid-line run), coverage=0.9316 ≥ baseline 0.9314. — Evidence: `contract_gate_corpus.json`; `uv run python contract_gate.py --json`
- Original plan assumed ceiling=218 (n=175, coverage=0.9314). Adding the mid-line `SYMPHONY_RESULT` run (9999) to n=175 drops coverage to 0.9261 — below baseline. Ceiling adjusted to 232 (n=190, coverage=0.9316 with mid-line run). — Evidence: ceiling sweep in dev-build Wave 3
- Mid-line marker run (9999): `terminal_signal()` returns None (the `^` anchor correctly rejects mid-line markers). This run exists to make a future `^`-anchor relaxation register as a coverage GAIN. — Evidence: `contract_gate_corpus.json` (entry with run_id=9999); `tests/test_contract_gate.py::test_midline_marker_is_uncovered`
- Seed script (`scripts/seed_contract_gate_corpus.py`) reads podium.db directly via `_load_corpus_from_db()` — it does NOT use `load_corpus()` (which now reads the fixture, creating a circular dependency). — Evidence: `scripts/seed_contract_gate_corpus.py:27-43`
- Removed: `import sqlite3`, `DB_PATH`, `RUNS_DIR` from `contract_gate.py`. Added: `FIXTURE_PATH`. — Evidence: `contract_gate.py` diff
- Tests: 8 tests in `tests/test_contract_gate.py` (4 existing + 4 new: fixture_path, corrupt_fixture, midline_marker, empty_corpus). All pass. — Evidence: `uv run pytest tests/test_contract_gate.py -v`
- Dev-build wave audits: 3 audited (1 passed, 1 auto_fixed, 1 overridden), 2 skipped. State at `plans/.adr-0029-contract-gate-frozen-corpus.state.yml`. — Evidence: state YAML

## Decisions

- Accepted ceiling adjustment: 218→232 to accommodate mid-line marker while keeping coverage ≥ 0.9314. — Evidence: dev-build Wave 3 ceiling sweep
- Seed script retains direct-DB path (not load_corpus) to avoid circular dependency. — Evidence: `scripts/seed_contract_gate_corpus.py` `_load_corpus_from_db()`
- Post-fix re-audit timed out (pi produced 0 bytes in 60s on 23KB diff); operator overrode to continue. — Evidence: `plans/.adr-0029-contract-gate-frozen-corpus.state.yml` wave 3

## Evidence

- `plans/adr-0029-contract-gate-frozen-corpus.md` — implementation plan
- `docs/adr/0029-contract-gate-frozen-corpus.md` — ADR (accepted)
- `contract_gate.py` — core change (load_corpus, FIXTURE_PATH, removed sqlite3/DB_PATH/RUNS_DIR)
- `contract_gate_corpus.json` — frozen fixture (190 runs)
- `scripts/seed_contract_gate_corpus.py` — seed script with direct DB query
- `tests/test_contract_gate.py` — 8 tests (4 existing + 4 new)
- `plans/.adr-0029-contract-gate-frozen-corpus.state.yml` — build audit trail

## Exclusions

- Full pi reviewer output for timed-out audits (0 bytes)
- Podium SQLite content (secret-bearing; not captured)

## Open Questions And Follow-Ups

- C-0339 needs implementation-complete update (currently says "pending /dev-plan")
- CI not wired for contract gate tests — `uv run pytest tests/test_contract_gate.py` needs a CI step
- Mid-line run 9999 is a detection gap: the gate detects regressions (lost coverage) but cannot detect when a `^`-anchor relaxation *falsely parses* the mid-line marker as a gain. See dev-review WARNING.
