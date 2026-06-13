# Session Capture: Unify Symphony agent output contract and clean the comment stream

- Date: 2026-06-13
- Purpose: Finish, verify, and land an in-flight refactor (#046) that was uncommitted at session start, then commit all three affected repos and update the wiki.
- Scope: Captured the output-contract design, the comment-stream cleanup, the claim-time source change, and the cross-repo WORKFLOW.md updates. Excluded routine priming chatter.

## Durable Facts

- A single Symphony output contract now lives in one place. `prompt_renderer.OUTPUT_CONTRACT` is a module constant appended to every rendered prompt (after the issue block), so the pi and claude runners receive identical end-of-run instructions from one source instead of duplicating boilerplate across `claude_runner._wrap_prompt` and each binding's `WORKFLOW.md`. — Evidence: `prompt_renderer.py` (`OUTPUT_CONTRACT`, `render_prompt`), commit `82f81fd`
- Agent summaries now use a multi-line `SYMPHONY_SUMMARY_BEGIN` / `SYMPHONY_SUMMARY_END` block (markdown, multi-line) rather than the single-line `SYMPHONY_SUMMARY:` marker, which truncated output. `scheduler._parse_summary_block` takes the last block across streams, strips ANSI and machine marker lines (`SYMPHONY_(RESULT|SUMMARY|COST_USD|INPUT_TOKENS|OUTPUT_TOKENS):`), and bounds it via `_bound_summary_block` (4000 chars; head 2500 / tail 1200 on overflow). The single-line marker remains a fallback in `_extract_summary` (block preferred, marker second). — Evidence: `scheduler.py` (`_SUMMARY_BLOCK_RE`, `_parse_summary_block`, `_bound_summary_block`, `_extract_summary`)
- Summaries are posted verbatim: `tracker_podium.post_comment` writes `body.strip()` directly, dropping the previous `### Symphony AI Summary` header wrapper. — Evidence: `tracker_podium.py` `post_comment`
- The machine `Timeline` footer was removed entirely — `_format_timeline`, the module-level `_CODE_SHA`, and the now-unused `from code_version import resolve_code_sha` import are gone from `scheduler.py`. `code_version.resolve_code_sha` is still used by `main.py:213` and keeps its own tests; only the dead scheduler usage was removed. — Evidence: `scheduler.py` diff, `main.py:213`
- The `Symphony claimed at <ts>` claim comment is no longer posted. Claim time now reads from the Run record's `started_at` via the new `scheduler._run_started_at` (uses `adapter.get_run` + `issue.latest_run_id`), with comment-parse fallback retained in `_claimed_at` for adapters without a Run store (Plane). `CLAIM_PREFIX` and the comment-parse path stay for Plane and historical issues. — Evidence: `scheduler.py` (`_run_started_at`, `_claimed_at`)
- The blocked-path comment now uses the verbatim summary (`msg = summary`) instead of `Agent reported a blocked result: {summary}`, and the stderr summary is appended only when there is no summary block. — Evidence: `scheduler.py` `run_tick` blocked branch
- Both live binding `WORKFLOW.md` files were updated to defer the contract to the engine-appended block and note the single-line fallback. homelab's edit is broader: it also documents thin-engine-v2 git ownership (agent owns all local git, no run branches/worktrees/auto-commit, commit to base branch before plane done/review, `tickets/{{issue.identifier}}.md` for notes) and renumbers/rewrites plan and build mode. Both bumped `run_timeout_ms` 1800000 → 3600000 (60 min, matching `config.py` default and C-0144). — Evidence: `/home/james/homelab/WORKFLOW.md` (commit `f1b7e57`), `/home/james/trading/crypto-trading-agents/WORKFLOW.md` (commit `9a29dfb`)
- `uv run pytest` is green: 694 passed, 1 skipped, ~66s. — Evidence: session test run

## Decisions

- Land the refactor as kanban issue #046 and commit all three repos (James chose "Commit all 3 repos + wiki"). — Evidence: session AskUserQuestion answer
- Commit binding `WORKFLOW.md` edits with honest messages covering their full scope (thin-engine git ownership + timeout bump), not mislabeling them as #046-only, because the diffs were broader than the output-contract change. — Evidence: `f1b7e57`, `9a29dfb`
- No `git push` and no `symphony-host.service` restart this session — neither was requested and both are gated by CLAUDE.md. The new code is on disk and committed locally but not yet running in the live service. — Evidence: CLAUDE.md safety section

## Evidence

- `82f81fd` — symphony commit: code + tests + `.kanban/issues/046-unified-output-contract.md`
- `f1b7e57` — homelab WORKFLOW.md commit
- `9a29dfb` — crypto-trading-agents WORKFLOW.md commit
- `scheduler.py`, `prompt_renderer.py`, `tracker_podium.py`, `claude_runner.py` — implementation
- `tests/test_scheduler.py`, `tests/test_prompt_renderer.py`, `tests/test_tracker_podium.py`, `tests/test_engine_against_podium.py` — coverage

## Exclusions

- No secrets read; `/home/james/symphony-host.env` not touched.
- Full transcript not archived.

## Open Questions And Follow-Ups

- The committed symphony code is not yet live: `symphony-host.service` still runs the previous code until a (James-approved) restart. The new comment format (no Timeline, verbatim summary block) only takes effect after restart.
- homelab `WORKFLOW.md` still references `plane done/review/blocked` helpers and Plane comments; the homelab Plane project is still active (archive deferred per C-0104). Consistent for now, but a homelab Plane archive would need another WORKFLOW pass.
- Verify on the first live run after restart that the multi-line summary block is parsed and posted verbatim with no Timeline footer and no claim comment.
