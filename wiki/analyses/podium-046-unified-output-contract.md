---
title: "#046 Unify agent output contract and clean the comment stream"
type: analysis
status: promoted
created: 2026-06-13
updated: 2026-06-23
sources:
  - .kanban/issues/046-unified-output-contract.md
  - prompt_renderer.py
  - scheduler.py
  - scheduler/__init__.py
  - scheduler/markers.py
  - scheduler/sanitize.py
  - tracker_podium.py
  - claude_runner.py
  - tests/test_scheduler.py
  - tests/test_schedule.py
  - tests/test_prompt_renderer.py
  - tests/test_tracker_podium.py
  - tests/test_engine_against_podium.py
  - wiki/raw/sessions/2026-06-13-unified-output-contract.md
  - wiki/raw/sessions/2026-06-13-046-live-output-contract-smoke.md
  - wiki/raw/sessions/2026-06-15-issue-max-question-verdict-drift.md
  - wiki/raw/sessions/2026-06-19-approval-gate-output-contract-false-positive.md
  - wiki/raw/sessions/2026-06-19-approval-gate-report-truncation-marker-drop.md
  - .kanban/issues/052-question-park.md
  - .kanban/issues/094-symphony-schedule-marker.md
  - runs/242.log
confidence: high
tags: [podium, dispatch, output-contract, summary, comments, claim-time, workflow, scheduling]
---

# #046 Unify agent output contract and clean the comment stream

Issue #046 collapses the agent end-of-run contract into one engine-owned source and strips machine noise from the human comment stream. Before it, the `SYMPHONY_RESULT`/`SYMPHONY_SUMMARY` boilerplate was duplicated across `claude_runner._wrap_prompt` and each binding's `WORKFLOW.md`, the single-line `SYMPHONY_SUMMARY:` marker truncated multi-line output, and every closing comment carried a machine `Timeline` footer plus a `Symphony claimed at <ts>` claim comment [source: .kanban/issues/046-unified-output-contract.md; source: wiki/raw/sessions/2026-06-13-unified-output-contract.md].

## One output contract

`prompt_renderer.OUTPUT_CONTRACT` is a module constant appended to every rendered prompt after the issue block, so the pi and claude runners receive identical instructions from one place [source: prompt_renderer.py]. The contract tells the agent to emit exactly one terminal outcome: `SYMPHONY_RESULT: done|review` plus a `SYMPHONY_SUMMARY_BEGIN` / `SYMPHONY_SUMMARY_END` block, `SYMPHONY_RESULT: blocked` plus a summary block, the #052 Question Park block `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END` when operator clarification is needed, or — as of #94 — `SYMPHONY_SCHEDULE: not_before=<next_window|iso8601-with-offset> reason="..."` plus a summary block when deferring to a maintenance window [source: prompt_renderer.py#29-36; source: .kanban/issues/052-question-park.md; source: .kanban/issues/094-symphony-schedule-marker.md]. Result summaries hold the natural end-of-turn message, written for a human reader, posted verbatim, bounded to ~4000 characters; question blocks are bounded by the same path [source: prompt_renderer.py; source: scheduler.py]. `claude_runner._wrap_prompt` now references the shared contract and permits Question Park instead of forbidding questions [source: claude_runner.py].

## Multi-line summary block

`scheduler._parse_summary_block(*streams)` returns the last `SYMPHONY_SUMMARY_BEGIN`/`SYMPHONY_SUMMARY_END` block across streams, preserving markdown and newlines [source: scheduler.py]. It strips ANSI, removes machine marker lines (`SYMPHONY_(RESULT|SCHEDULE|SUMMARY|COST_USD|INPUT_TOKENS|OUTPUT_TOKENS):` via `_MARKER_LINE_RE`), and bounds the result with `_bound_summary_block` — pass-through under 4000 chars, otherwise head 2500 + a truncation notice + tail 1200 — so a runaway agent cannot smuggle its whole transcript into a comment that is later re-injected as untrusted prompt context [source: scheduler/markers.py#37-40]. `_extract_summary` prefers the block, then falls back to the legacy single-line `_parse_summary_marker` [source: scheduler.py]. This is a companion to the verdict/schedule marker contract: the marker line declares the terminal mechanism; the block carries the prose.

## Question Park block (#052)

`scheduler._parse_question_block(*streams)` returns the last `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END` block, strips ANSI/marker lines, and `_extract_question` redacts secrets before bounding with the same summary bound [source: scheduler.py]. In `run_tick`, a question block after a clean agent exit records the Run as `succeeded` with verdict `question`, posts `**Symphony question:**` with the extracted text, transitions the Issue to `in_review`, and notifies review; `SYMPHONY_RESULT: blocked` still takes the unchanged blocked path before question handling [source: scheduler.py; source: tests/test_scheduler.py; source: .kanban/issues/052-question-park.md]. This makes Question Park a third terminal outcome of the shared output contract, not a new issue state or separate state machine.

**Known live drift (2026-06-15):** `symphony` Issue `25` / Run `36` showed that the scheduler's `verdict="question"` persistence path does not match the Podium schema: `run.verdict` and `issue.latest_verdict` still allow only `done|review|blocked`, so `_finish_run_record` raised a SQLite CHECK error after a clean agent exit. The Issue moved to `in_review` via stale-running fallback while the latest Run stayed `running`. See [podium-question-park-verdict-drift](podium-question-park-verdict-drift.md) and C-0211 [source: wiki/raw/sessions/2026-06-15-issue-max-question-verdict-drift.md].

## Approval-gate precedence fix (2026-06-19)

Podium issue #53 (`Homelab workflow`) exposed a second output-contract precedence bug: Claude runs 111 and 113 emitted explicit terminal markers (`SYMPHONY_RESULT: review` then `SYMPHONY_RESULT: done`), but the scheduler still blocked the issue because `_classify_terminal` checked `_hit_approval_gate(...)` before parsing the result/question markers. The broad approval regex matched successful policy-summary prose such as `destructive actions without explicit approval` and `destructive actions without James approval` [source: wiki/raw/sessions/2026-06-19-approval-gate-output-contract-false-positive.md].

The fix preserves markerless approval-needed blocking but makes explicit contract markers authoritative for approval-gate classification: `_classify_terminal` now extracts `verdict`, `summary`, and `question` before the approval gate, and only runs `_hit_approval_gate(...)` when both `verdict is None` and `question is None`. Permission-gate handling still precedes result handling. Regression coverage asserts the two known policy phrases inside a `SYMPHONY_RESULT: done` summary transition to review instead of blocked [source: scheduler/__init__.py; source: tests/test_scheduler.py; source: wiki/raw/sessions/2026-06-19-approval-gate-output-contract-false-positive.md].

### Follow-on: report-truncation marker drop (2026-06-19, C-0257)

The same false positive recurred on issues #53/#55/#57 (run 120) even on a service that already had the precedence fix. Distinct root cause: `_classify_terminal` parsed the verdict marker and gates from the **2 KB tail-truncated** `_format_report` output (`_parse_result_marker(stdout)`, `_hit_*_gate(stdout, ...)`). `_format_report` → `_sanitize_report(..., max_bytes=REPORT_MAX_BYTES=2048)` keeps only the trailing 2048 bytes, so an agent summary larger than ~2 KB pushed the head `SYMPHONY_RESULT` marker out of the surviving tail → `verdict=None` while approval-policy prose in the tail re-tripped `_hit_approval_gate` → spurious `approval-gate` block. The precedence guard could not help because the marker was dropped before parsing; `_extract_summary`/`_extract_question` already read the raw streams, making this an inconsistency [source: scheduler/sanitize.py; source: scheduler/__init__.py; source: runs/120.log].

The fix classifies verdict + permission/approval gates from the raw `result.stdout`/`result.stderr` streams (`class_stdout`/`class_stderr`, gated by `parse_stderr`), mirroring `_extract_summary`; the truncated `_format_report` output is retained only for bounded human-facing comments. `_parse_result_marker`, `_hit_permission_gate`, and `_hit_approval_gate` strip ANSI internally so feeding raw streams preserves the prior sanitized-input matching. Regression test `test_verdict_marker_honored_when_summary_exceeds_report_truncation` (head marker + >`REPORT_MAX_BYTES` summary + tail approval prose) fails pre-fix (`approval-gate`) and passes post-fix (`agent-marker-review`). Deployed live (commit `2cf2eb2`), reproduced on smoke Issue 58 / Run 122 (succeeded, verdict=done) with an offline `runs/122.log` probe confirming the old truncated-parse path would have blocked, and the three stuck issues 53/55/57 were requeued (`PATCH state=todo`) and re-ran clean to `in_review` [source: scheduler/__init__.py; source: scheduler/markers.py; source: tests/test_scheduler.py; source: wiki/raw/sessions/2026-06-19-approval-gate-report-truncation-marker-drop.md].

### Follow-on: END marker glued to trailing text (2026-06-23, Run #242)

Run #242 had a valid multi-line summary in `runs/242.log`, but the closing marker appeared as `SYMPHONY_SUMMARY_ENDAcknowledged — ...` because additional prose was appended on the same line. The old `_SUMMARY_BLOCK_RE` required `SYMPHONY_SUMMARY_END` to terminate the line, so `_parse_summary_block` returned `None`; the scheduler therefore stored `run.summary=NULL` and posted only `**Symphony completed:** Agent finished without a summary.` to Issue #97 despite the summary being present in the log [source: runs/242.log; source: scheduler/markers.py].

Commit `0ac7c5e` makes `_SUMMARY_BLOCK_RE` treat the `SYMPHONY_SUMMARY_END` token as closing the block even when non-newline text trails it, while still capturing only the block body. Regression `test_summary_block_tolerates_text_appended_to_end_marker_line` mirrors the Run #242 shape and asserts the trailing text is excluded [source: scheduler/markers.py; source: tests/test_schedule.py]. The live `podium.db` row for Run #242 / Issue #97 was backfilled from `runs/242.log` after the fixed parser extracted the existing summary.

## Verbatim posting, no header wrapper

`tracker_podium.post_comment` writes `body.strip()` straight into `comments_md`, dropping the prior `### Symphony AI Summary` header wrapper so the agent's summary lands verbatim [source: tracker_podium.py]. The blocked branch of `run_tick` likewise uses the verbatim summary (`msg = summary`) rather than `Agent reported a blocked result: {summary}`, and only appends the stderr summary when no summary block is present [source: scheduler.py].

## Timeline footer and claim comment removed

The machine `Timeline` footer is gone: `_format_timeline`, the module-level `_CODE_SHA`, and the now-unused `from code_version import resolve_code_sha` import were deleted from `scheduler.py` [source: scheduler.py]. `code_version.resolve_code_sha` survives — it is still used by `main.py:213` and keeps its own tests; only the dead scheduler usage was removed [source: main.py]. The `Symphony claimed at <ts>` claim comment is no longer posted; claim time is now read from the Run record's `started_at` via the new `_run_started_at` (`adapter.get_run` + `issue.latest_run_id`), with the comment-parse path in `_claimed_at` retained as a fallback for adapters without a Run store (Plane) and for historical issues. `CLAIM_PREFIX` stays for that Plane fallback [source: scheduler.py].

## WORKFLOW.md updates across repos

Both live binding `WORKFLOW.md` files were updated and committed in their own repos to defer the contract to the engine-appended block and note the single-line fallback. The homelab edit is broader: it also documents thin-engine-v2 git ownership (agent owns all local git, no run branches/worktrees/auto-commit, commit to base branch before `plane done`/`review`, `tickets/{{issue.identifier}}.md` for issue-scoped notes) and renumbers/rewrites plan and build mode. Both bumped `run_timeout_ms` 1800000 → 3600000 (60 min, matching `config.py` and C-0144) [source: wiki/raw/sessions/2026-06-13-unified-output-contract.md].

## Review hardening (post-`82f81fd`)

An independent Opus review of the committed change surfaced five issues, all fixed as a follow-up [source: scheduler.py; source: prompt_renderer.py]:

- **Secret-redaction order (security).** `_parse_summary_block` no longer bounds; it returns the full cleaned block and `_extract_summary` redacts secrets *before* calling `_bound_summary_block` (gated by an `is_block` flag; the single-line marker is already capped). Previously bounding ran first, so a secret straddling the 2500-char head boundary could leak a surviving fragment [source: scheduler.py].
- **Contract example self-match.** `_SUMMARY_BLOCK_RE` now requires the markers at the **start of a line** (`^SYMPHONY_SUMMARY_BEGIN`, no leading `[ \t]*`), and `OUTPUT_CONTRACT` instructs agents to emit them unindented. The contract's own indented example can no longer be parsed as a real block if an agent echoes the prompt into its stream [source: scheduler.py; source: prompt_renderer.py].
- **Plane fallback overhead.** `_run_started_at` gates on `getattr(adapter, "stores_context", False)` before any call, so Plane (whose `get_run` exists but returns None) short-circuits instead of paying a `get_issue` API request every reconcile tick [source: scheduler.py].
- **Heading fidelity.** A present summary is posted as `**Symphony completed:**\n\n{summary}` (own line) so a leading markdown heading renders [source: scheduler.py].
- **Notifier bound.** The blocked-reason text sent to Telegram is capped at `NOTIFY_REASON_MAX_CHARS = 2000` (comment keeps the full body) so the ~4000-char summary cannot push the message past Telegram's 4096-char limit and silently drop the alert [source: scheduler.py].

Accepted without change: `_MARKER_LINE_RE` could in principle strip a human line beginning `SYMPHONY_x:` (low risk); `comments_md` blob growth from larger summaries (no regression, prompt re-injection still capped at 12000); the claim→`started_at` orphan window (pre-existing, startup reaper still catches it).

## Verification and live status

`uv run pytest` is green (696 passed, 1 skipped — base 694 plus two review-hardening tests: secret-straddle redaction and indented-block non-match). The base change is committed across three repos (`82f81fd` symphony, `f1b7e57` homelab, `9a29dfb` trading); the review-hardening follow-up is a separate symphony commit (`5be9755`). Both are now pushed to `origin/main` and live — `symphony-host.service` was restarted on `5be9755` at 2026-06-13 04:48 UTC [source: wiki/raw/sessions/2026-06-13-unified-output-contract.md].

## Live verification (2026-06-13)

The contract was verified end-to-end on the running service via a low-risk homelab smoke Issue (James-approved). A successful Pi/codex Run (`provider=openai-codex model=gpt-5.5:low`, verdict `done`, exit 0, ~37s) produced `comments_md` equal to `**Symphony completed:**\n\n{summary}`, where `{summary}` was the agent's multi-line `SYMPHONY_SUMMARY_BEGIN`/`END` block posted **verbatim** (three markdown bullets, newlines preserved). The comment carried no `### Symphony AI Summary` header, no `**Timeline** —` footer, and the Issue's comment stream held no `Symphony claimed at` comment — confirming the C-0160 / C-0161 / C-0162 behavior in production (C-0166). `run.summary` stored the block verbatim; `comments_md` was that block plus the prefix. The Claude dispatch path (C-0154) was not exercised [source: wiki/raw/sessions/2026-06-13-046-live-output-contract-smoke.md].

A first attempt failed for an unrelated reason: `reasoning_effort=minimal` (valid in Symphony's `IssueCreate`) is rejected by the default `gpt-5.5` model, which supports only `none`/`low`/`medium`/`high`/`xhigh`. The agent exited non-zero in ~8s and the Issue went `blocked`/`failed`; the blocked comment still showed the #046-clean format (no Timeline, no claim comment) and posted the stderr summary because no summary block was emitted. Re-filing with `reasoning_effort=low` succeeded. This effort/model incompatibility is captured as C-0167 [source: wiki/raw/sessions/2026-06-13-046-live-output-contract-smoke.md].
