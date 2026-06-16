---
title: "Claude refeed session-id collision (claude_ready_timeout)"
type: analysis
status: promoted
created: 2026-06-16
updated: 2026-06-16
sources:
  - claude_runner.py
  - session_continuity.py
  - scheduler.py
  - tests/test_claude_runner.py
  - wiki/raw/sessions/2026-06-16-claude-refeed-session-id-collision.md
confidence: high
tags: [podium, dispatch, claude, tmux, session-resume, refeed, bugfix]
---

# Claude refeed session-id collision (claude_ready_timeout)

## Symptom

Issue 27's claude runs 54 and 55 both failed with `state=failed`, `verdict=blocked`, exit 1, after exactly ~30s (`READY_TIMEOUT_SECONDS`). The run logs showed only `claude_ready_timeout` and `no server running on /tmp/symphony-claude-27-<nonce>.sock` [source: wiki/raw/sessions/2026-06-16-claude-refeed-session-id-collision.md]. Runs 45-49 of the same issue had succeeded earlier (verdict `review`, resumed sessions); the failures began after a service restart that dispatched the issue without resume eligibility.

## Root cause

`derive_session_id(issue_id)` is a deterministic UUID5, so every dispatch of an issue targets the same claude transcript at `~/.claude/projects/<encoded-cwd>/<session_id>.jsonl` [source: session_continuity.py]. Pre-fix, `run_claude_agent` selected the launch flag from the `resumed` flag alone:

```python
session_arg = "--resume" if resume_requested else "--session-id"
```

`claude --session-id <id>` **creates** a session and aborts when a transcript for that id already exists (`Error: Session ID <id> is already in use.`, exit 1); `claude --resume <id>` **attaches** to it. Confirmed empirically against the claude CLI: `--session-id` on an existing id exits 1, `--resume` on the same id exits 0 [source: wiki/raw/sessions/2026-06-16-claude-refeed-session-id-collision.md].

A refeed dispatch arrives with `resumed=false` but the deterministic transcript from the earlier successful runs is still on disk. Forcing `--session-id` there collided, claude exited before readiness, the per-run tmux server died, and the 30s `_wait_until_ready` poll reported `claude_ready_timeout` (and, on teardown capture, `no server running`) [source: claude_runner.py].

The refeed was triggered by `sha-drift`: the symphony binding is a self-binding on the scheduler's own repo (C-0170), which the agent keeps committing to, so the working-tree SHA always drifts from the session's anchored `agent_session_sha`. `evaluate_resume_eligibility` returns `refeed`/`sha-drift`, `resume_skipped ... fell_back=true`, `resumed=false` — so the collision recurred on every poll, a permanent failure loop until fixed [source: session_continuity.py] [source: scheduler.py].

## Fix

Choose the launch flag by transcript existence, not the `resumed` flag:

```python
session_arg = "--resume" if (resume_requested or transcript_file.exists()) else "--session-id"
```

`--resume` attaches to an existing transcript (no collision); `--session-id` is used only when no transcript exists. The `resumed` flag still governs prompt **content** upstream (incremental comment prompt vs full re-feed in `scheduler._render_for_dispatch`), and no longer drives the launch flag. The fix is non-destructive — it preserves the existing transcript and the deterministic-id contract, and a refeed still re-sends the full prompt [source: claude_runner.py].

Coverage: only the transcript-exists case (sha-drift refeed) flips to `--resume`. The other refeed reasons stay on `--session-id` create because no claude transcript exists — agent-mismatch (pi→claude), cwd-missing (cwd-keyed path absent), session-absent, and fresh issues [source: session_continuity.py].

## Verification

- Regression test `tests/test_claude_runner.py::test_claude_refeed_uses_resume_when_transcript_already_exists` asserts `--resume` is emitted when a transcript exists and `resumed=false`. Full suite: 841 passed, 2 skipped [source: tests/test_claude_runner.py].
- Empirical claude-CLI repro confirmed the collision premise and the `--resume` fix.
- Landed as commit `4521730` (fix hunk + test only); live in the running service (the fixed file was on disk before the restart).

## Relationship to prior knowledge

Refines the Session Resume continuity model (ADR-0009): the resume/refeed decision controls prompt content, but the claude adapter must still attach to an existing transcript regardless of that decision. Complements the #042 Claude tmux adapter analysis (ready poll, `symphony-claude-<issue>-<nonce>` artifacts, completion gate) by documenting a session-flag failure mode of that same adapter.
