# Session Capture: Claude refeed session-id collision (issue 27 runs 54/55)

- Date: 2026-06-16
- Purpose: Diagnose why issue 27's claude runs 54 and 55 failed `claude_ready_timeout`, and fix so it cannot recur.
- Scope: Root cause, the fix in `claude_runner.py`, empirical confirmation against the claude CLI, and verification. Issue 27 recovery was intentionally out of scope (operator chose to forget it and only prevent recurrence).

## Durable Facts

- `derive_session_id(issue_id)` is a deterministic UUID5, so every dispatch of a given issue targets the **same** claude transcript path `~/.claude/projects/<encoded-cwd>/<session_id>.jsonl`. — Evidence: `session_continuity.py` `derive_session_id` / `session_file_path`
- `claude --session-id <id>` aborts with `Error: Session ID <id> is already in use.` (exit 1) when a transcript for that id exists; `claude --resume <id>` attaches to the same id (exit 0). — Evidence: live repro in a throwaway `/tmp` cwd with a one-off UUID (steps 1 create → 2 `--session-id` collide exit 1 → 3 `--resume` exit 0)
- Before the fix, `claude_runner.run_claude_agent` chose the launch flag from the `resumed` flag alone: `session_arg = "--resume" if resume_requested else "--session-id"`. A refeed (`resumed=false`) therefore forced `--session-id` against the already-existing deterministic transcript → claude exited before readiness → the tmux server died → the 30s `_wait_until_ready` poll surfaced `claude_ready_timeout` + `no server running on /tmp/symphony-claude-<issue>-<nonce>.sock`. — Evidence: `runs/54.log`, `runs/55.log`; pre-fix `claude_runner.py` line ~407
- A refeed happens whenever resume is ineligible. For issue 27 the reason was `sha-drift`: the binding is a self-binding on Symphony's own repo, which the agent keeps committing to, so the working-tree SHA always drifts from the session's anchored `agent_session_sha`. Resume is skipped (`resume_skipped reason=sha-drift fell_back=true`), `resumed=false`, and the collision recurs on every poll — a permanent failure loop until fixed. — Evidence: `journalctl` `resume_skipped issue_id=27 reason=sha-drift`; `run.agent_session_sha` column (runs 45-49=`89a17b1`, 54=`ccd22ff`, 55=`ca01062`); `session_continuity.evaluate_resume_eligibility` REASON_SHA_DRIFT
- The `resumed` flag governs prompt **content** upstream (incremental comment prompt vs full re-feed), not the claude launch flag. — Evidence: `scheduler.py` `_render_for_dispatch` / `_prepare_resume_candidate` (`if comments_text and not resumed`)

## Decisions

- Fix: choose the claude launch flag by **transcript existence**, not the `resumed` flag — `session_arg = "--resume" if (resume_requested or transcript_file.exists()) else "--session-id"`. Non-destructive (preserves the existing transcript and the deterministic-id contract); a refeed still re-sends the full prompt. — Evidence: commit `4521730`, `claude_runner.py`
- Committed as an isolated commit (fix hunk + regression test only); the unrelated `ask_user_question` prompt-wording change in the same file was intentionally left unstaged. — Evidence: `git show 4521730 --stat`
- Push deferred: local `main` was 8 commits ahead of `origin/main`, 7 authored by other sessions (ADR-0012 RemoteAgentAdapter work); operator to decide whether to push all 8. — Evidence: `git log --oneline origin/main..HEAD`

## Evidence

- `claude_runner.py` (lines ~404-419) — the `session_arg` selection now keyed on `transcript_file.exists()`.
- `tests/test_claude_runner.py::test_claude_refeed_uses_resume_when_transcript_already_exists` — regression test; asserts `--resume` is emitted when a transcript exists and `resumed=false`. Full suite: 841 passed, 2 skipped.
- `runs/54.log`, `runs/55.log` — `claude_ready_timeout` / `no server running on ...sock`.
- `podium.db` `run` table — issue 27 runs 45-49 succeeded (review, resumed), 54/55 failed (blocked) on the first restart that ran without resume eligibility.
- Live claude CLI repro confirming the collision premise (cleaned up after).

## Exclusions

- No secrets, env values, or `symphony-host.env` contents.
- Issue 27 recovery steps (operator de-scoped).
- Full transcript not archived.

## Open Questions And Follow-Ups

- Push decision for the 8 unpushed commits on `main` (operator-owned).
- The running service loaded the fixed `claude_runner.py` (mtime 02:20 < restart 02:40), so the fix is live, but it has not yet been exercised by a real refeed dispatch — first natural claude refeed will confirm in production.
