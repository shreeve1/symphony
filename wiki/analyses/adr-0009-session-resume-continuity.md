---
title: ADR-0009 — Session-resume continuity, best-effort over a re-feed floor
type: analysis
status: promoted
created: 2026-06-13
updated: 2026-06-14
sources:
  - wiki/raw/adr-0009-session-resume-continuity.md
  - docs/adr/0009-session-resume-continuity.md
  - wiki/raw/sessions/2026-06-13-session-resume-continuity-design.md
  - .kanban/issues/050-pi-resume-end-to-end.md
  - .kanban/issues/051-claude-resume-end-to-end.md
  - .kanban/issues/052-question-park.md
  - .kanban/issues/053-live-session-tail.md
  - .kanban/issues/054-fast-redispatch-on-reply.md
  - .kanban/issues/055-checkpointed-exploration.md
  - .claude/skills/checkpointed-exploration/SKILL.md
  - .claude/skills/symphony-workflow-author/SKILL.md
  - scheduler.py
  - agent_runner.py
  - claude_runner.py
  - prompt_renderer.py
  - web/api/main.py
  - web/api/wake_signal.py
  - web/api/tests/test_session_tail.py
  - web/api/tests/test_reply.py
  - web/frontend/components/IssueFlyout.tsx
  - web/frontend/components/QueryProvider.tsx
  - web/frontend/components/SessionTailPanel.tsx
  - web/frontend/tests/session-tail.spec.ts
  - tests/test_scheduler.py
confidence: high
tags: [adr, session-resume, continuity, re-feed, decision, checkpointed-exploration, implemented]
---

# ADR-0009 — Session-resume continuity

## Decision

Continue a parked Issue by **resuming the coding agent's own on-disk CLI session** rather than re-feeding the curated `comments_md`/`context_md` blobs — but only as a **best-effort optimization layered over the stateless re-feed, which stays the guaranteed floor**. Reverses (conditionally, at design stage) the deliberate stateless-continuity stance recorded in [operator-reply](../concepts/operator-reply.md) (`operator-reply.md:60-62`) and implied by [ADR-0005](adr-0005-replace-plane-with-podium.md). [source: wiki/raw/adr-0009-session-resume-continuity.md]

## Key decisions captured

- **Goal**: continuity *quality* — make the review-reply loop feel like the agent CLI. Resume only pays off if it lets the follow-up prompt *stop* re-feeding full context.
- **Derive, don't capture**: session id = `UUIDv5(namespace, issue.id)`; the Issue is the session key, nothing drifts from disk. Stay on the tmux/CLI path (ADR-0001), not the Agent SDK. pi `--session-id`; Claude `--session-id` (first run) / `--resume` (subsequent), branch chosen by a filesystem probe.
- **Eligibility predicate** (all four or fall back to re-feed): same agent kind ∧ cwd exists+unchanged ∧ session file present ∧ git HEAD unchanged since the session last ran (`run.agent_session_sha`). Confines resume to the **in_review/blocked → reply** loop; Done-reopen and predicate failures re-feed; worktree lifecycle (#021) untouched.
- **Delta-only resume prompt**: mechanical wrapper + newest operator-reply block only; Issue body/Comments/Context/WORKFLOW omitted (in-session). Symphony keeps writing the blobs (UI + fallback) but stops injecting on resume; #026 compaction is skipped on resume runs.
- **Persistence**: two nullable `run` columns — `agent_session_sha` and `resumed` (observability). No pointer table; id stays derived; existence is a probe.
- **Silent-failure guardrail**: never `--continue` (silent-fresh on mismatch); explicit id fails loud; runtime resume errors are caught and re-fed in the same tick with `resume_skipped`/`resume_failed` markers.

## Rejected alternatives

- **Capture the agent-minted id** (idiomatic Claude SDK approach) — would force an Agent-SDK migration retiring the hardened tmux adapter (#042–#046), or a fragile `.jsonl` scrape; no pi equivalent. Derive is symmetric and SDK-free.
- **`issue_session` pointer table** — second source of truth that can disagree with disk, storing a derivable value.
- **Keep worktrees alive after merge** so Done-reopen can resume — fights the #021 lifecycle for the rarest case; re-feed covers it.
- **Native auto-compaction replacing #026** — deferred, not adopted (two context stores; reconciliation is a separate decision).

## Accepted costs / reversibility

Continuity now depends on hidden filesystem state (`~/.claude/projects`, `~/.pi/agent/sessions`) needing retention; WORKFLOW edits mid-park are invisible to a resume run until fallback; agent/model swaps and base-branch advances force re-feed. All bounded by the floor — worst case is today's behavior. Reversible per-Issue and globally with no schema rollback (columns nullable, unread by fallback).

## Scope note

`accepted` and implemented through the between-Run continuity backlog as of 2026-06-14. Implemented slices: #047 run columns, #048 pure decision core (`session_continuity.py` + `tests/test_session_continuity.py`), #049 delta-only resume prompt rendering (`render_prompt(..., resume=True)`), #050 pi RPC dispatch/resume wiring, #051 Claude tmux resume wiring, #052 Question Park, #053 Live Session Tail, #054 Fast re-dispatch, and #055 Checkpointed exploration. Pi RPC and Claude runs can now take the Session Resume path when eligibility passes; ineligible and runtime-failed paths still fall back to re-feed. Question Park adds a `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END` outcome that parks the issue to `in_review`, posts the question, and relies on the existing operator-reply redispatch/resume path for the answer. Session Tail adds a web/API-process read-only JSONL tailer that emits `run.tail` WebSocket events to the flyout without changing the scheduler process model. Fast re-dispatch adds a filesystem wake sentinel touched by replies/state-to-`todo` PATCHes and consumed by the scheduler during poll sleeps so the next candidate scan starts within the short sentinel interval instead of waiting the full poll. Checkpointed exploration adds a repo-local Skill and prompt directive that force one bounded exploration step per Run followed by Question Park review. #056/#057/#058 add pi RPC Steering follow-ups. See [session-resume-continuity concept](../concepts/session-resume-continuity.md).

## Claims

C-0175, C-0177, C-0180, C-0181, C-0182, C-0183, C-0184, C-0185, C-0186, C-0187, and C-0192 in [CLAIMS.md](../CLAIMS.md).
