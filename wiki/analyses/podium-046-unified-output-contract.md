---
title: "#046 Unify agent output contract and clean the comment stream"
type: analysis
status: promoted
created: 2026-06-13
updated: 2026-06-13
sources:
  - .kanban/issues/046-unified-output-contract.md
  - prompt_renderer.py
  - scheduler.py
  - tracker_podium.py
  - claude_runner.py
  - tests/test_scheduler.py
  - tests/test_prompt_renderer.py
  - tests/test_tracker_podium.py
  - tests/test_engine_against_podium.py
  - wiki/raw/sessions/2026-06-13-unified-output-contract.md
  - wiki/raw/sessions/2026-06-13-046-live-output-contract-smoke.md
  - .kanban/issues/052-question-park.md
confidence: high
tags: [podium, dispatch, output-contract, summary, comments, claim-time, workflow]
---

# #046 Unify agent output contract and clean the comment stream

Issue #046 collapses the agent end-of-run contract into one engine-owned source and strips machine noise from the human comment stream. Before it, the `SYMPHONY_RESULT`/`SYMPHONY_SUMMARY` boilerplate was duplicated across `claude_runner._wrap_prompt` and each binding's `WORKFLOW.md`, the single-line `SYMPHONY_SUMMARY:` marker truncated multi-line output, and every closing comment carried a machine `Timeline` footer plus a `Symphony claimed at <ts>` claim comment [source: .kanban/issues/046-unified-output-contract.md; source: wiki/raw/sessions/2026-06-13-unified-output-contract.md].

## One output contract

`prompt_renderer.OUTPUT_CONTRACT` is a module constant appended to every rendered prompt after the issue block, so the pi and claude runners receive identical instructions from one place [source: prompt_renderer.py]. The contract tells the agent to emit exactly one terminal outcome: `SYMPHONY_RESULT: done|review` plus a `SYMPHONY_SUMMARY_BEGIN` / `SYMPHONY_SUMMARY_END` block, `SYMPHONY_RESULT: blocked` plus a summary block, or the #052 Question Park block `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END` when operator clarification is needed [source: prompt_renderer.py; source: .kanban/issues/052-question-park.md]. Result summaries hold the natural end-of-turn message, written for a human reader, posted verbatim, bounded to ~4000 characters; question blocks are bounded by the same path [source: prompt_renderer.py; source: scheduler.py]. `claude_runner._wrap_prompt` now references the shared contract and permits Question Park instead of forbidding questions [source: claude_runner.py].

## Multi-line summary block

`scheduler._parse_summary_block(*streams)` returns the last `SYMPHONY_SUMMARY_BEGIN`/`SYMPHONY_SUMMARY_END` block across streams, preserving markdown and newlines [source: scheduler.py]. It strips ANSI, removes machine marker lines (`SYMPHONY_(RESULT|SUMMARY|COST_USD|INPUT_TOKENS|OUTPUT_TOKENS):` via `_MARKER_LINE_RE`), and bounds the result with `_bound_summary_block` — pass-through under 4000 chars, otherwise head 2500 + a truncation notice + tail 1200 — so a runaway agent cannot smuggle its whole transcript into a comment that is later re-injected as untrusted prompt context [source: scheduler.py]. `_extract_summary` prefers the block, then falls back to the legacy single-line `_parse_summary_marker` [source: scheduler.py]. This is a companion to the verdict marker contract (see C-0006): the verdict line still declares done/review/blocked; the block now carries the prose.

## Question Park block (#052)

`scheduler._parse_question_block(*streams)` returns the last `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END` block, strips ANSI/marker lines, and `_extract_question` redacts secrets before bounding with the same summary bound [source: scheduler.py]. In `run_tick`, a question block after a clean agent exit records the Run as `succeeded` with verdict `question`, posts `**Symphony question:**` with the extracted text, transitions the Issue to `in_review`, and notifies review; `SYMPHONY_RESULT: blocked` still takes the unchanged blocked path before question handling [source: scheduler.py; source: tests/test_scheduler.py; source: .kanban/issues/052-question-park.md]. This makes Question Park a third terminal outcome of the shared output contract, not a new issue state or separate state machine.

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
