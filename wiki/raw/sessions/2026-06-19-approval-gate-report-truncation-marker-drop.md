# Session Capture: Approval-Gate Block from Report-Truncation Marker Drop

- Date: 2026-06-19
- Purpose: Capture the follow-on root cause and fix for issues #53/#55/#57 still blocking on clean agent exits after C-0256, plus live deploy, smoke reproduction, and issue recovery.
- Scope: Scheduler terminal classification reading truncated vs raw streams, the fix, live restart, a crafted smoke reproduction, and requeue recovery of the three stuck issues.

## Durable Facts

- After C-0256 (fix `27ea8d7`, live) made explicit result/question markers authoritative for approval-gate classification, issues #53/#55 and new #57 (run 120) still classified `blocked` on clean agent exits (`exit_code=0`). Service was on `code_sha=53b31ac`, which already contained `27ea8d7`. Evidence: `runs/120.log`, journal `agent_exited exit_code=0 -> state_transitioned blocked -> dispatch_completed reason=approval-gate`.
- Distinct root cause from C-0256: `_classify_terminal` parsed the verdict marker and gates from the **2 KB tail-truncated** `_format_report` output (`_parse_result_marker(stdout)`, `_hit_permission_gate(stdout, ...)`, `_hit_approval_gate(stdout, ...)` at `scheduler/__init__.py:1624,1628,1656`). `_format_report` calls `_sanitize_report(..., max_bytes=REPORT_MAX_BYTES=2048)` which keeps only the trailing 2048 bytes. When an agent emitted a summary larger than ~2 KB, the head `SYMPHONY_RESULT` marker fell outside the surviving tail → `verdict=None`, while approval-policy prose still present in the tail tripped `_hit_approval_gate` → spurious `approval-gate` block. The C-0256 marker-authoritative guard could not help because the marker itself was being dropped before parsing. Evidence: `runs/120.log` is 6896 bytes; offline probe shows marker present in raw (`done`) but absent in the 2072-byte truncated copy, approval prose present in both.
- `_extract_summary`/`_extract_question` already parsed the raw `result.stdout`/`result.stderr` streams (`scheduler/sanitize.py:104-136`), so only the verdict marker and the two gate checks were reading the truncated copy — an inconsistency.
- Fix (`2cf2eb2`): `_classify_terminal` now classifies verdict + permission/approval gates from the raw `result.stdout`/`result.stderr` streams (`class_stdout`/`class_stderr`, gated by `parse_stderr`), mirroring `_extract_summary`. The truncated `stdout`/`stderr` from `_format_report` are still used for the bounded human-facing comments. `_parse_result_marker`, `_hit_permission_gate`, and `_hit_approval_gate` (`scheduler/markers.py`) now strip ANSI internally so feeding raw streams preserves the prior sanitized-input matching behavior. Evidence: `scheduler/__init__.py`, `scheduler/markers.py` diff.
- Regression coverage: `test_verdict_marker_honored_when_summary_exceeds_report_truncation` (`tests/test_scheduler.py`) files a run whose stdout has a head `SYMPHONY_RESULT: done` followed by a >`REPORT_MAX_BYTES` summary block with approval prose in the tail; it fails pre-fix (`reason=approval-gate`) and passes post-fix (`reason=agent-marker-review`). Verified: temporarily reverting the `class_stdout` change made the new test report `approval-gate`; restoring made it pass. Full suite `uv run pytest -q` → 936 passed, 2 skipped.
- Live deploy: committed `2cf2eb2`, restarted `symphony-host.service` (operator-approved as-is despite a concurrent session's unrelated dirty tree). Post-restart `symphony_started code_sha=2cf2eb2 bindings=5`, all 5 bindings `reconcile_startup_begin/done`, `dispatch_completed` alive, `rpc_orphan_reap_done count=0`, `pi_rpc_probe_ok`, zero errors.
- Live reproduction: smoke Issue 58 / Run 122 on the `symphony` binding (agent=pi, provider=openai-codex, model=`gpt-5.5:high`, `agent_session_sha=2cf2eb2`) instructed the agent to emit a head `SYMPHONY_RESULT: done` then a >3 KB summary with tail approval prose. Run succeeded, verdict=done, Issue → `in_review`. Offline simulation on the real `runs/122.log` (6896 B): OLD truncated-parse path → verdict None + approval present → would block (`approval-gate`); NEW raw-parse path → verdict `done`. Issue 58 left in Podium as audit evidence.
- Recovery: the three stuck issues were requeued via `PATCH /api/issues/{id} {"state":"todo"}` (fires `touch_wake_sentinel()`). 53 was `archived` (not just blocked), 55/57 `blocked`. All three re-dispatched on `2cf2eb2` (runs 123/124/125), succeeded with verdict=done, and moved to `in_review`.

## Decisions

- Terminal classification (verdict marker + permission/approval gates) must read the raw agent streams, never the truncation-bounded `_format_report` output. The 2 KB report bound is for human-facing comment readability only and must not gate machine classification. Evidence: operator request to fix the recurring block; `scheduler/__init__.py` implementation.
- Issue 53 was requeued out of `archived` as part of the operator "requeue" instruction; flag for re-archive if it was deliberately archived.

## Evidence

- `scheduler/__init__.py` — `_classify_terminal` raw-stream classification (`class_stdout`/`class_stderr`).
- `scheduler/markers.py` — `_parse_result_marker`/`_hit_permission_gate`/`_hit_approval_gate` ANSI-strip internally.
- `scheduler/sanitize.py` — `_sanitize_report` tail-truncation (`REPORT_MAX_BYTES=2048`) and raw-stream `_extract_summary`.
- `tests/test_scheduler.py` — `test_verdict_marker_honored_when_summary_exceeds_report_truncation`.
- `runs/120.log`, `runs/122.log` — pre-fix false-positive and post-fix reproduction outputs.
- Commit `2cf2eb2`.

## Exclusions

- No secrets, credentials, cookies, or `/home/james/symphony-host.env` contents captured.
- No raw full transcripts captured.
- Did not capture the concurrent session's unrelated uncommitted changes (ssh_support.py, frontend, remote-binding wiki work).

## Open Questions And Follow-Ups

- Optional `_APPROVAL_GATE_RE` tightening (so quoted policy prose doesn't match) was deliberately not implemented; the truncation fix resolves the reported symptom and benign-phrase tests pass. Revisit if markerless false positives recur.
- Confirm whether issue 53 should remain active (`in_review`) or be re-archived.
