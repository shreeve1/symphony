# Session Capture: Approval Gate Output Contract False Positive

- Date: 2026-06-19
- Purpose: Capture the root cause and fix for Podium issue #53 repeatedly blocking after a successful Claude run.
- Scope: Scheduler output-contract parsing, approval-gate precedence, regression tests, and verification status.

## Durable Facts

- Podium issue #53 (`Homelab workflow`) had two clean Claude runs that emitted terminal output-contract markers but still ended `failed/blocked`: run 111 emitted `SYMPHONY_RESULT: review`, run 113 emitted `SYMPHONY_RESULT: done`. Evidence: `/home/james/symphony/runs/111.log`, `/home/james/symphony/runs/113.log`, and read-only SQLite inspection of `podium.db`.
- Root cause: `_classify_terminal` evaluated `_hit_approval_gate(...)` before parsing and honoring `SYMPHONY_RESULT`/`SYMPHONY_QUESTION`; the broad approval regex matched policy-summary prose such as `destructive actions without explicit approval` and `destructive actions without James approval`. Evidence: `scheduler/__init__.py`, `scheduler/markers.py`, and a local probe using `_APPROVAL_GATE_RE` against the two run logs.
- Fix: `_classify_terminal` now parses `verdict`, `summary`, and `question` before approval-gate handling, and the approval gate only fires when both explicit result and question markers are absent. Permission-gate handling remains ahead of result handling. Evidence: `scheduler/__init__.py` diff.
- Regression coverage: `test_approval_gate_does_not_override_explicit_result_summary` asserts that the two known policy phrases inside a `SYMPHONY_RESULT: done` summary move the issue to review rather than blocked. Existing markerless approval-needed coverage remains. Evidence: `tests/test_scheduler.py` diff.
- Verification: `/home/james/.local/bin/uv run pytest tests/test_scheduler.py -k 'approval_gate' -q` passed (5 tests); `/home/james/.local/bin/uv run ruff check scheduler/__init__.py tests/test_scheduler.py` passed. Full `tests/test_scheduler.py` run timed out at 180 seconds after partial progress; no failure assertion was observed before timeout.

## Decisions

- Explicit output-contract markers take precedence over the broad approval-gate heuristic for approval-gate classification. Evidence: operator request to patch the false block and `scheduler/__init__.py` implementation.

## Evidence

- `scheduler/__init__.py` — terminal classification order and approval-gate condition.
- `scheduler/markers.py` — broad `_APPROVAL_GATE_RE` that remains useful for markerless approval-needed exits.
- `tests/test_scheduler.py` — regression coverage for explicit result markers containing approval-policy prose.
- `/home/james/symphony/runs/111.log` and `/home/james/symphony/runs/113.log` — original false-positive run outputs.

## Exclusions

- No secrets, credentials, env files, cookies, or `/home/james/symphony-host.env` contents captured.
- No raw full transcript captured.
- No DB mutations, service restarts, or pushes performed.

## Open Questions And Follow-Ups

- Full `tests/test_scheduler.py` should be rerun when the environment is clear enough for a longer validation window.
- Operator can manually transition or retry issue #53 if desired; this session did not mutate issue state.
