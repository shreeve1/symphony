---
title: ADR-0009 — Session-resume continuity, best-effort over a re-feed floor
type: analysis
status: promoted
created: 2026-06-13
updated: 2026-06-13
sources:
  - wiki/raw/adr-0009-session-resume-continuity.md
  - docs/adr/0009-session-resume-continuity.md
  - wiki/raw/sessions/2026-06-13-session-resume-continuity-design.md
confidence: high
tags: [adr, session-resume, continuity, re-feed, decision, design-stage, partially-implemented]
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

`accepted` and **partially implemented** as of 2026-06-13. Live behavior is still pure re-feed because adapters are not wired yet. Implemented slices: #047 run columns, #048 pure decision core (`session_continuity.py` + `tests/test_session_continuity.py`), and #049 delta-only resume prompt rendering (`render_prompt(..., resume=True)`). Remaining backlog `.kanban/issues/050`–`055` covers pi/Claude end-to-end resume, Question Park, Session Tail, fast re-dispatch, and checkpointed exploration; #056/#057/#058 add pi RPC Steering follow-ups. See [session-resume-continuity concept](../concepts/session-resume-continuity.md).

## Claims

C-0175, C-0177, and C-0180 in [CLAIMS.md](../CLAIMS.md).
