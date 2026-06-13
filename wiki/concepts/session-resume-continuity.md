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
  - .kanban/issues/050-pi-resume-end-to-end.md
  - .kanban/issues/051-claude-resume-end-to-end.md
  - .kanban/issues/052-question-park.md
  - agent_runner.py
  - claude_runner.py
  - scheduler.py
  - prompt_renderer.py
  - tests/test_claude_runner.py
  - tests/test_dispatch_compaction.py
  - tests/test_scheduler.py
  - tests/test_prompt_renderer.py
confidence: high
tags: [session-resume, continuity, re-feed, question-park, session-tail, design-stage, partially-implemented, podium]
---

# Session Resume continuity

> **Partially implemented as of 2026-06-13.** Schema columns (#047), the pure decision core (#048), delta-only prompt rendering (#049), **pi RPC resume wiring (#050)**, **Claude resume wiring (#051)**, and **Question Park (#052)** have landed. Live tail (#053), fast redispatch (#054), and checkpointed exploration (#055) remain pending.

## The two continuity modes

Symphony's **Continuity** model is how a re-dispatched Issue picks up where the agent left off. Two modes (CONTEXT.md glossary: Continuity / Re-feed / Session Resume):

- **Re-feed** — stateless, the guaranteed floor. Re-render full `comments_md` + `context_md` into a fresh prompt; a new process re-reads them. This is today's only mode and stays the fallback. [source: wiki/concepts/operator-reply.md]
- **Session Resume** — stateful optimization. Resume the agent's own on-disk CLI session (verbatim conversation history) via a derived id, sending only the new operator-reply delta. Best-effort. [source: docs/adr/0009-session-resume-continuity.md]

A session persists the **conversation, not the filesystem** — resume restores what the agent read/decided, not the working tree. [source: wiki/raw/sessions/2026-06-13-session-resume-continuity-design.md]

## Mechanics (ADR-0009)

- **Derived id** `UUIDv5(namespace, issue.id)` — the Issue is the session key; nothing stored to drift. pi `--session-id`; Claude `--session-id` (create) / `--resume` (resume), branch by filesystem probe of the cwd-namespaced session file. Stays on the tmux/CLI path (ADR-0001), not the Agent SDK. Implemented in `session_continuity.derive_session_id` as `uuid.uuid5(uuid.NAMESPACE_URL, f"symphony.issue:{issue_id}")` for #048. [source: session_continuity.py]
- **cwd coupling** — sessions are namespaced by working directory (Claude `~/.claude/projects/<encoded-cwd>/<id>.jsonl`; pi `~/.pi/agent/sessions/<cwd-slug>/`). Resume only works when cwd is stable+present. Implemented path helpers honor `PI_CODING_AGENT_SESSION_DIR` and existing timestamp-prefixed pi session files. [source: session_continuity.py]
- **Eligibility predicate** (all four, else re-feed): same agent kind ∧ cwd present+unchanged ∧ session file present ∧ git HEAD unchanged since the session last ran (`run.agent_session_sha`). Scope: in_review/blocked reply loop only; Done-reopen falls back; worktree lifecycle (#021) untouched. Implemented as pure `evaluate_resume_eligibility(...)` returning stable `resume`/`refeed` actions and reasons (`agent-mismatch`, `cwd-missing`, `session-absent`, `sha-drift`). [source: session_continuity.py] [source: tests/test_session_continuity.py]
- **Delta-only prompt** — mechanical wrapper + newest operator-reply block only; Issue body/Comments/Context/WORKFLOW omitted. Symphony keeps writing the blobs for UI + fallback; #026 compaction skipped on resume runs. Implemented in #049 as `render_prompt(..., resume=True)`: the resume branch returns `OUTPUT_CONTRACT` plus the newest `### Operator Reply` block, and keeps the Podium `preferred_skill` directive when set. [source: prompt_renderer.py] [source: tests/test_prompt_renderer_podium.py]
- **Pi RPC dispatch (#050)** — `PiRpcAgentAdapter` launches `pi --mode rpc --provider ... --model ... --session-id <derive_session_id(issue.id)>` (plus `--skill <dir>` when present), sends the rendered prompt as a JSON command on stdin, pumps JSONL events until `agent_end`, sends `abort` on timeout, and maps the final assistant text into `AgentResult.stdout` so verdict/summary parsing stays adapter-neutral. One-shot `PiAgentAdapter` remains the default rollback path; bindings opt into RPC with `pi_mode: rpc`. [source: agent_runner.py] [source: config.py] [source: main.py]
- **Claude tmux dispatch (#051)** — `run_claude_agent` now derives the same session id and launches fresh Claude runs with `--session-id <derived>` and resumed Claude runs with `--resume <derived>`; it never uses `--continue` / `-c`. Scheduler resume eligibility now covers Claude as well as pi RPC, so eligible Claude resume runs get the delta-only prompt, skip context compaction, record `resumed`/`agent_session_sha`, and fall back to fresh full re-feed on resume exceptions or non-zero results. [source: claude_runner.py] [source: scheduler.py] [source: tests/test_claude_runner.py] [source: tests/test_dispatch_compaction.py]
- **Run observability** — Run rows carry `agent_session_sha` and `resumed`. Scheduler computes the current dispatch cwd/git sha, evaluates #048 eligibility for pi RPC and Claude bindings, records these fields when starting Run rows, skips `_maybe_compact_context` on resume, and falls back to fresh full re-feed on predicate miss or resume runtime/non-zero failure with `resume_skipped` / `resume_failed ... fell_back=true` markers. [source: scheduler.py] [source: tracker_podium.py] [source: tests/test_dispatch_compaction.py]
- **Question Park (#052)** — `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END` is a third terminal outcome in the shared output contract. Scheduler extracts the question, records the Run with verdict `question`, posts `**Symphony question:**` as the Issue comment, and transitions the Issue to `in_review`; blocked-on-error remains the existing `SYMPHONY_RESULT: blocked` path. Claude's wrapper permits this protocol instead of forbidding questions, while Pi receives it through the same rendered `OUTPUT_CONTRACT`. [source: prompt_renderer.py] [source: claude_runner.py] [source: scheduler.py] [source: tests/test_scheduler.py] [source: .kanban/issues/052-question-park.md]
- **Silent-failure guardrail** — never `--continue`; explicit id fails loud; runtime/non-zero resume errors are caught and re-fed in-tick (`resume_skipped`/`resume_failed`).

[source: docs/adr/0009-session-resume-continuity.md]

## Paired CLI-fidelity features (same design)

- **Question Park** — landed in #052. The agent may park to `in_review` carrying a clarifying question via `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END`, and the operator reply resumes the session with the answer. Turn-taking; only useful because resume preserves the thread. [source: CONTEXT.md] [source: scheduler.py] [source: .kanban/issues/052-question-park.md]
- **Session Tail** — tail the live-appended session `.jsonl` and stream over the WS hub (#017) for in-flight visibility, without changing the separate-process scheduler model (ADR-0006). [source: CONTEXT.md]
- **Fast re-dispatch** — reply writes a wake sentinel the scheduler watches; round-trip minutes → seconds.
- **Checkpointed exploration** — WORKFLOW/Skill policy: bounded step then park, leaning on resume + Question Park.
- **Steering** (pi-only, live mid-run) — operator input injected into a *running* pi Run via the RPC `steer` command, distinct from the between-Run Question Park reply loop. Decided by **ADR-0010** (dispatch pi via `pi --mode rpc`); in-scope as #056/#057/#058. [source: CONTEXT.md] [source: docs/adr/0010-pi-rpc-dispatch-for-live-steering.md]
- Deferred (no issues): `--fork` A/B exploration. (Live mid-run steering is no longer deferred — un-deferred for pi via RPC by ADR-0010, C-0178; it was never viable for Claude, which has no headless protocol for this account and keeps park-and-reply.)

## Backlog

`.kanban/issues/047`–`055` plus ADR-0010 steering/RPC follow-ups. Status: 047 (run columns), 048 (decision core), 049 (delta renderer), **050 (pi RPC dispatch + resume wiring)**, **051 (Claude resume wiring)**, and **052 (Question Park)** are done; 053 Session Tail, 054 fast re-dispatch, and 055 checkpointed exploration remain pending; #056/#057/#058 cover pi RPC steering. [source: .kanban/issues/047-run-session-tracking-columns.md] [source: .kanban/issues/048-continuity-decision-core.md] [source: .kanban/issues/049-delta-only-resume-prompt.md] [source: .kanban/issues/050-pi-resume-end-to-end.md] [source: .kanban/issues/051-claude-resume-end-to-end.md] [source: .kanban/issues/052-question-park.md]

## Relation to existing knowledge

This conditionally reverses the "transcript re-feed, not session resume" stance in [operator-reply](operator-reply.md) (line 60-62) for **pi RPC and Claude runs that pass eligibility** — but **re-feed remains the floor**, so that page stays accurate for fallback, non-RPC Pi, and any ineligible run.

## Claims

C-0175, C-0176, C-0177, C-0178, C-0180, C-0181, C-0182, C-0183, C-0184, and C-0185 in [CLAIMS.md](../CLAIMS.md).
