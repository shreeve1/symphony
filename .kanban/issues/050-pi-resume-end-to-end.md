---
id: 050
title: Pi resume end-to-end (in_review reply loop)
status: pending
blocked_by: [047, 048, 049]
parent: null
priority: 0
created: 2026-06-13
---

## What to build

Wire the continuity decision core (#048) and delta-only renderer (#049) into the Pi adapter and scheduler dispatch, delivering the first working Session Resume tracer bullet for the in_review/blocked → operator-reply → re-dispatch loop.

On a reply-triggered re-dispatch:

- Evaluate `evaluate_resume_eligibility(...)`. If `resume`: launch `pi --print --session-id <derive_session_id(issue.id)> ...` (NOT `--no-session`, NOT `--continue`), render the delta-only resume prompt, set `resumed=true`, record `agent_session_sha = <HEAD at run start>`.
- If `refeed` (predicate failed) OR the resume launch errors at runtime (session vanished/corrupt): fall back within the same dispatch tick to a fresh session + full re-feed prompt (current behavior), `resumed=false`.
- Emit loud log markers: `resume_skipped reason=<...>` (predicate failure) and `resume_failed reason=<...> fell_back=true` (runtime error), mirroring the existing `claude_probe_failed` style.

Scope guard: resume only applies in the in_review/blocked reply loop. Done-reopen falls back to re-feed. The worktree lifecycle (#021 FF-merge + teardown on Done) is untouched.

Compaction interplay: **skip `_maybe_compact_context(...)` on resume runs** — `context_md` is not injected on resume, so there is nothing to compact. Fresh/fallback runs keep the existing compaction step.

## Acceptance criteria

- [ ] On a predicate-pass resume run, the Pi command includes `--session-id <derived>` and includes neither `--no-session` nor `--continue`.
- [ ] On a resume run, the rendered prompt is the delta-only prompt (#049); on a fallback run it is the full re-feed prompt.
- [ ] `resumed` and `agent_session_sha` are written to the `run` row correctly for both resume and fallback paths.
- [ ] Predicate failure and a simulated resume launch error both fall back to fresh+re-feed in the same tick and emit the documented log markers.
- [ ] `_maybe_compact_context` is NOT invoked on resume runs and IS invoked on fresh/fallback runs.
- [ ] Done-reopen path uses re-feed (never resume).

## Verification

`uv run pytest tests/test_dispatch_compaction.py tests/test_scheduler*.py tests/test_session_continuity.py -q`

## Blocked by

- Blocked by #047, #048, #049
