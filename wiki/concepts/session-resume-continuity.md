---
title: Session Resume continuity (partially implemented)
type: concept
status: promoted
created: 2026-06-13
updated: 2026-06-13
sources:
  - docs/adr/0009-session-resume-continuity.md
  - wiki/raw/adr-0009-session-resume-continuity.md
  - CONTEXT.md
  - wiki/raw/sessions/2026-06-13-session-resume-continuity-design.md
confidence: high
tags: [session-resume, continuity, re-feed, question-park, session-tail, design-stage, partially-implemented, podium]
---

# Session Resume continuity

> **Partially implemented as of 2026-06-13.** Schema columns (#047) and the pure decision core (#048) have landed, but live dispatch still uses pure text re-feed until #049–#051 wire rendering and adapters. This page records the agreed design (ADR-0009) and implementation status; it is NOT yet a description of live resume behavior.

## The two continuity modes

Symphony's **Continuity** model is how a re-dispatched Issue picks up where the agent left off. Two modes (CONTEXT.md glossary: Continuity / Re-feed / Session Resume):

- **Re-feed** — stateless, the guaranteed floor. Re-render full `comments_md` + `context_md` into a fresh prompt; a new process re-reads them. This is today's only mode and stays the fallback. [source: wiki/concepts/operator-reply.md]
- **Session Resume** — stateful optimization. Resume the agent's own on-disk CLI session (verbatim conversation history) via a derived id, sending only the new operator-reply delta. Best-effort. [source: docs/adr/0009-session-resume-continuity.md]

A session persists the **conversation, not the filesystem** — resume restores what the agent read/decided, not the working tree. [source: wiki/raw/sessions/2026-06-13-session-resume-continuity-design.md]

## Mechanics (ADR-0009)

- **Derived id** `UUIDv5(namespace, issue.id)` — the Issue is the session key; nothing stored to drift. pi `--session-id`; Claude `--session-id` (create) / `--resume` (resume), branch by filesystem probe of the cwd-namespaced session file. Stays on the tmux/CLI path (ADR-0001), not the Agent SDK. Implemented in `session_continuity.derive_session_id` as `uuid.uuid5(uuid.NAMESPACE_URL, f"symphony.issue:{issue_id}")` for #048. [source: session_continuity.py]
- **cwd coupling** — sessions are namespaced by working directory (Claude `~/.claude/projects/<encoded-cwd>/<id>.jsonl`; pi `~/.pi/agent/sessions/<cwd-slug>/`). Resume only works when cwd is stable+present. Implemented path helpers honor `PI_CODING_AGENT_SESSION_DIR` and existing timestamp-prefixed pi session files. [source: session_continuity.py]
- **Eligibility predicate** (all four, else re-feed): same agent kind ∧ cwd present+unchanged ∧ session file present ∧ git HEAD unchanged since the session last ran (`run.agent_session_sha`). Scope: in_review/blocked reply loop only; Done-reopen falls back; worktree lifecycle (#021) untouched. Implemented as pure `evaluate_resume_eligibility(...)` returning stable `resume`/`refeed` actions and reasons (`agent-mismatch`, `cwd-missing`, `session-absent`, `sha-drift`). [source: session_continuity.py] [source: tests/test_session_continuity.py]
- **Delta-only prompt** — mechanical wrapper + newest operator-reply block only; Issue body/Comments/Context/WORKFLOW omitted. Symphony keeps writing the blobs for UI + fallback; #026 compaction skipped on resume runs.
- **Two `run` columns** — `agent_session_sha`, `resumed`. No pointer table.
- **Silent-failure guardrail** — never `--continue`; explicit id fails loud; runtime errors caught and re-fed in-tick (`resume_skipped`/`resume_failed`).

[source: docs/adr/0009-session-resume-continuity.md]

## Paired CLI-fidelity features (same design)

- **Question Park** — flip the "never ask questions" wrapper; the agent may park to `in_review` carrying a clarifying question (`SYMPHONY_QUESTION`), and the operator reply resumes the session with the answer. Turn-taking; only useful because resume preserves the thread. [source: CONTEXT.md]
- **Session Tail** — tail the live-appended session `.jsonl` and stream over the WS hub (#017) for in-flight visibility, without changing the separate-process scheduler model (ADR-0006). [source: CONTEXT.md]
- **Fast re-dispatch** — reply writes a wake sentinel the scheduler watches; round-trip minutes → seconds.
- **Checkpointed exploration** — WORKFLOW/Skill policy: bounded step then park, leaning on resume + Question Park.
- Deferred (no issues): live tmux send-keys mid-run steering (Claude-only); `--fork` A/B exploration.

## Backlog

`.kanban/issues/047`–`055`. Status: 047 (run columns) and 048 (decision core) are done; 049 delta renderer remains the next unblocked resume slice; 050/051 wire pi/Claude end-to-end after 049; {052 Question Park → 055 checkpointed, 053 Session Tail}; 054 fast re-dispatch parallel after 047. [source: .kanban/issues/047-run-session-tracking-columns.md] [source: .kanban/issues/048-continuity-decision-core.md]

## Relation to existing knowledge

This conditionally reverses the "transcript re-feed, not session resume" stance in [operator-reply](operator-reply.md) (line 60-62) — but **re-feed remains the floor**, so that page stays accurate for fallback and for all pre-implementation behavior. Mark superseded only once Session Resume ships.

## Claims

C-0175, C-0176, C-0177 in [CLAIMS.md](../CLAIMS.md).
