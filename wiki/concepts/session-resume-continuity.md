---
title: Session Resume continuity
type: concept
status: promoted
created: 2026-06-13
updated: 2026-06-15
sources:
  - docs/adr/0009-session-resume-continuity.md
  - wiki/raw/adr-0009-session-resume-continuity.md
  - CONTEXT.md
  - wiki/raw/sessions/2026-06-13-session-resume-continuity-design.md
  - .kanban/issues/050-pi-resume-end-to-end.md
  - .kanban/issues/051-claude-resume-end-to-end.md
  - .kanban/issues/052-question-park.md
  - wiki/raw/sessions/2026-06-15-issue-max-question-verdict-drift.md
  - .kanban/issues/053-live-session-tail.md
  - .kanban/issues/054-fast-redispatch-on-reply.md
  - .kanban/issues/055-checkpointed-exploration.md
  - .kanban/issues/056-live-steer-channel.md
  - .kanban/issues/057-steer-ui-flyout.md
  - .kanban/issues/058-rpc-lifecycle-ops.md
  - .claude/skills/checkpointed-exploration/SKILL.md
  - .claude/skills/symphony-workflow-author/SKILL.md
  - agent_runner.py
  - claude_runner.py
  - scheduler.py
  - prompt_renderer.py
  - tests/test_claude_runner.py
  - tests/test_dispatch_compaction.py
  - tests/test_scheduler.py
  - tests/test_prompt_renderer.py
  - web/api/main.py
  - web/api/wake_signal.py
  - web/api/steer_queue.py
  - web/api/tests/test_session_tail.py
  - web/api/tests/test_reply.py
  - web/api/tests/test_steer.py
  - web/frontend/components/IssueFlyout.tsx
  - web/frontend/components/SessionTailPanel.tsx
  - web/frontend/components/QueryProvider.tsx
  - web/frontend/tests/session-tail.spec.ts
  - web/frontend/tests/steer-flyout.spec.ts
  - tests/test_scheduler.py
confidence: high
tags: [session-resume, continuity, re-feed, question-park, session-tail, checkpointed-exploration, implemented, podium]
---

# Session Resume continuity

> **Implemented through the between-Run continuity backlog as of 2026-06-14.** Schema columns (#047), the pure decision core (#048), delta-only prompt rendering (#049), **pi RPC resume wiring (#050)**, **Claude resume wiring (#051)**, **Question Park (#052)**, **Live Session Tail (#053)**, **Fast re-dispatch (#054)**, and **Checkpointed exploration (#055)** have landed. Live mid-run Steering is ADR-0010 work: **#056 live steer channel**, **#057 flyout UI**, and **#058 RPC lifecycle hardening** have landed.

## The two continuity modes

Symphony's **Continuity** model is how a re-dispatched Issue picks up where the agent left off. Two modes (CONTEXT.md glossary: Continuity / Re-feed / Session Resume):

- **Re-feed** — stateless, the guaranteed floor. Re-render full `comments_md` + `context_md` into a fresh prompt; a new process re-reads them. Stays the fallback whenever Session Resume is ineligible. [source: wiki/concepts/operator-reply.md]
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
- **Question Park (#052)** — `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END` is a third terminal outcome in the shared output contract. Scheduler extracts the question, records the Run with verdict `question`, posts `**Symphony question:**` as the Issue comment, and transitions the Issue to `in_review`; blocked-on-error remains the existing `SYMPHONY_RESULT: blocked` path. Claude's wrapper permits this protocol instead of forbidding questions, while Pi receives it through the same rendered `OUTPUT_CONTRACT`. **Known drift:** Issue `25` / Run `36` proved the persisted verdict path currently fails against Podium SQLite because the schema excludes `question` from `run.verdict` / `issue.latest_verdict`; until fixed, a Question Park can leave the Issue `in_review` while latest Run remains `running`. [source: prompt_renderer.py] [source: claude_runner.py] [source: scheduler.py] [source: tests/test_scheduler.py] [source: .kanban/issues/052-question-park.md] [source: wiki/raw/sessions/2026-06-15-issue-max-question-verdict-drift.md]
- **Silent-failure guardrail** — never `--continue`; explicit id fails loud; runtime/non-zero resume errors are caught and re-fed in-tick (`resume_skipped`/`resume_failed`).

[source: docs/adr/0009-session-resume-continuity.md]

## Paired CLI-fidelity features (same design)

- **Question Park** — landed in #052. The agent may park to `in_review` carrying a clarifying question via `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END`, and the operator reply resumes the session with the answer. Turn-taking; only useful because resume preserves the thread. Live caveat: persisted verdict `question` currently violates Podium CHECK constraints (C-0211), so the storage path needs repair. [source: CONTEXT.md] [source: scheduler.py] [source: .kanban/issues/052-question-park.md] [source: wiki/raw/sessions/2026-06-15-issue-max-question-verdict-drift.md]
- **Session Tail (#053)** — the web/API process tails live-appended pi/Claude session `.jsonl` files for running issues and publishes appended lines as `run.tail` events over the existing in-process WS hub (#017), without changing the separate-process scheduler model (ADR-0006). `_SessionTailer` resolves the derived session path, reads byte ranges in `rb` mode only, tracks cursor/inode per issue, emits existing content on first detection, and treats missing/empty/locked files as no event. The flyout's Session tab renders lines from the shared `QueryProvider` WebSocket stream and filters by issue id. [source: web/api/main.py] [source: web/api/tests/test_session_tail.py] [source: web/frontend/components/SessionTailPanel.tsx] [source: web/frontend/components/QueryProvider.tsx] [source: web/frontend/tests/session-tail.spec.ts]
- **Fast re-dispatch (#054)** — successful operator replies and API PATCH transitions to `todo` touch a filesystem wake sentinel. The scheduler consumes the sentinel during its poll sleep at a one-second cadence, clears it with `unlink`, and immediately starts another candidate scan; absent sentinel preserves normal poll cadence, and a stale sentinel is consumed without sleeping so restart cannot wedge the loop. Config knobs: `SYMPHONY_WAKE_SENTINEL_PATH`, else `SYMPHONY_RUNTIME_DIR/reply-wake`, else `/tmp/symphony/reply-wake`. [source: web/api/wake_signal.py] [source: web/api/main.py] [source: scheduler.py] [source: web/api/tests/test_reply.py] [source: tests/test_scheduler.py]
- **Checkpointed exploration (#055)** — a repo-local `checkpointed-exploration` Skill plus prompt-renderer directive tells agents to do exactly one bounded exploration step, summarize evidence, then park with `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END` until the operator replies; it emits only when that Skill is selected and is documented in `symphony-workflow-author` guidance. [source: .claude/skills/checkpointed-exploration/SKILL.md] [source: prompt_renderer.py] [source: tests/test_prompt_renderer_podium.py] [source: .kanban/issues/055-checkpointed-exploration.md]
- **Steering** (pi-only, live mid-run) — operator input injected into a *running* pi Run via the RPC `steer` command, distinct from the between-Run Question Park reply loop. Decided by **ADR-0010** and implemented through #056/#057/#058: the API writes transient steer/abort queue records plus durable `Operator Steer` / `Operator Abort` comment blocks, the pi RPC adapter forwards queue records to stdin, the flyout Session tab exposes steer/abort controls only for active pi RPC runs, and #058 clears per-run/stale steer queue files on adapter exit and startup reaping. [source: CONTEXT.md] [source: docs/adr/0010-pi-rpc-dispatch-for-live-steering.md] [source: web/api/main.py] [source: web/api/steer_queue.py] [source: agent_runner.py] [source: web/frontend/components/IssueFlyout.tsx] [source: web/frontend/tests/steer-flyout.spec.ts] [source: .kanban/issues/058-rpc-lifecycle-ops.md]
- Deferred (no issues): `--fork` A/B exploration. (Live mid-run steering is no longer deferred — un-deferred for pi via RPC by ADR-0010, C-0178; it was never viable for Claude, which has no headless protocol for this account and keeps park-and-reply.)

## Backlog

`.kanban/issues/047`–`055` plus ADR-0010 steering/RPC follow-ups. Status: 047 (run columns), 048 (decision core), 049 (delta renderer), **050 (pi RPC dispatch + resume wiring)**, **051 (Claude resume wiring)**, **052 (Question Park)**, **053 (Live Session Tail)**, **054 (Fast re-dispatch)**, **055 (Checkpointed exploration)**, **056 (Live Steering channel)**, **057 (flyout Steering UI)**, and **058 (pi RPC lifecycle/ops hardening)** are done. [source: .kanban/issues/047-run-session-tracking-columns.md] [source: .kanban/issues/048-continuity-decision-core.md] [source: .kanban/issues/049-delta-only-resume-prompt.md] [source: .kanban/issues/050-pi-resume-end-to-end.md] [source: .kanban/issues/051-claude-resume-end-to-end.md] [source: .kanban/issues/052-question-park.md] [source: .kanban/issues/053-live-session-tail.md] [source: .kanban/issues/054-fast-redispatch-on-reply.md] [source: .kanban/issues/055-checkpointed-exploration.md] [source: .kanban/issues/056-live-steer-channel.md] [source: .kanban/issues/057-steer-ui-flyout.md] [source: .kanban/issues/058-rpc-lifecycle-ops.md]

## Relation to existing knowledge

This **supersedes** the original "transcript re-feed, not session resume" stance in [operator-reply](operator-reply.md) (that section is now marked superseded): Session Resume is live for eligible pi RPC and Claude runs — but **re-feed remains the floor**, so that page's historical paragraph stays accurate for any ineligible run (agent/cwd/SHA change, missing session).

## Claims

C-0175, C-0176, C-0177, C-0178, C-0180, C-0181, C-0182, C-0183, C-0184, C-0185, C-0186, C-0187, C-0192, C-0193, C-0194, and C-0211 in [CLAIMS.md](../CLAIMS.md).
