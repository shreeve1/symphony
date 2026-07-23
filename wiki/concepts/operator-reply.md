---
title: Operator reply comments
type: concept
status: promoted
created: 2026-06-12
updated: 2026-07-23
sources:
  - web/api/main.py
  - scheduler/stamp.py
  - scheduler/reconcile.py
  - tests/test_scheduler.py
  - docs/handoffs/2026-07-21-018-podium-issue-chat-spec.md
  - prompt_renderer.py
  - web/frontend/components/IssueFlyout.tsx
  - web/frontend/tests/reply.spec.ts
  - web/api/tests/test_reply.py
  - web/api/tests/test_comment.py
  - web/api/wake_signal.py
  - scheduler.py
  - plans/feature-operator-reply-comments.md
  - docs/adr/0017-comment-as-primitive-reopen-as-separate-effect.md
confidence: high
tags: [operator-reply, comments_md, re-dispatch, todo-flip, podium, prompt-renderer, issue-flyout]
---

# Operator reply comments (`POST /api/issues/{id}/reply`)

> **Issue-chat follow-on (2026-07-23; parent #37 remains open):** new `comments_md` writes now use the uniform `### <role> · <UTC-ts>` wrapper. `/comment` keeps its append-only/no-reopen semantics but the API now stamps it `operator`; scheduler-generated turns use `agent`, or `patrol` when `CandidateIssue.origin == "patrol"`, including pending-review reconciliation. Commit `934ff60` fixed the last patrol-attribution gap. Full issue-chat acceptance is still blocked by #38–#41, so this note records the landed write contract rather than declaring the whole spec complete. [source: scheduler/stamp.py] [source: scheduler/reconcile.py] [source: web/api/main.py] [source: tests/test_scheduler.py] [source: docs/handoffs/2026-07-21-018-podium-issue-chat-spec.md]

The operator-reply feature lets the operator continue the AI conversation from the flyout's comments tab: posting a reply both records an attributed comment and re-dispatches the agent. It closes the gap between the bidirectional Issue Comments intent (`CONTEXT.md:75`: operator writes instructions/feedback, AI writes are append-only, both read) and the prior implementation, which had no structured operator-write path and nothing flipping an issue back to `todo` after the agent parked it [source: plans/feature-operator-reply-comments.md].

## The endpoint

`POST /api/issues/{issue_id}/reply` accepts a JSON body `{ "body": str }` (validated by a `ReplyCreate` Pydantic model: `min_length=1`, `extra="forbid"`, plus a field validator that strips and rejects whitespace-only). Auth is the existing global `/api/` middleware [source: web/api/main.py].

On success it performs four effects in one transaction:

1. Appends an attributed block `\n\n### Operator Reply (<ISO-timestamp>)\n\n<body>` to `comments_md`.
2. Flips `state` to `todo`.
3. Bumps `updated_at` (monotonic, via `_next_updated_at`).
4. Publishes an `issue.updated` WebSocket event and returns the updated row.

After the durable write and publish, #054 touches the scheduler wake sentinel so re-dispatch can happen within the short sentinel check interval instead of the full poll interval. Failed guarded replies do not touch the sentinel. [source: web/api/main.py] [source: web/api/wake_signal.py] [source: web/api/tests/test_reply.py]

### Atomic write and guards

The append + state flip is a **single conditional SQL `UPDATE`** that concatenates server-side — `comments_md = COALESCE(comments_md, '') || ?` — with the state/run-state guard in its `WHERE` clause, avoiding the read-modify-write race the Python-side append helpers are subject to. `COALESCE` is required because SQLite's `NULL || text` yields `NULL`, which would silently drop the reply on a legacy/direct-write row while still flipping state [source: web/api/main.py] [source: web/api/tests/test_reply.py].

`rowcount == 0` is disambiguated by a follow-up `SELECT` into 404 (issue gone) vs 409 (guard failed).

Allowed source states are `in_review`, `blocked`, `done` only, AND the issue's `latest_run_state` must not be `queued`/`running` (an issue can sit in an allowed state while a run row is still active). Error contract:

| Condition | Status |
|-----------|--------|
| `running`/`todo` issue state | 409 |
| allowed state but `latest_run_state` in `queued`/`running` | 409 |
| empty/whitespace body | 422 |
| unknown extra key | 400 |
| unknown issue id | 404 |

[source: web/api/main.py] [source: web/api/tests/test_reply.py]

> Note: the 422 whitespace-body case required stripping the non-JSON-serializable `ctx` from the Pydantic `errors()` before raising `HTTPException`, because the custom `field_validator` leaves a raw `ValueError` in `ctx` [source: web/api/main.py].

## Re-dispatch by `todo`-flip

The endpoint only sets `todo`; it does not dispatch directly. The scheduler still picks the issue up via the existing candidate scan and re-runs the agent, so re-dispatch obeys the binding's existing approval/schedule gates — no second dispatch path is introduced. #054 speeds this up by touching a filesystem sentinel (`SYMPHONY_WAKE_SENTINEL_PATH`, else `SYMPHONY_RUNTIME_DIR/reply-wake`, else `/tmp/symphony/reply-wake`) that `scheduler.run_loop` consumes during its sleep wait, clears, and uses to immediately start another scan. **The durable new fact is that posting an operator reply carries a `todo` state-flip side effect plus a wake-sentinel side effect.** [source: web/api/main.py] [source: web/api/wake_signal.py] [source: scheduler.py] [source: tracker_podium.py]

A reply on a `done` issue silently reopens it (→ `todo`). No new worktree code is needed: `create_worktree` already reuses an orphan branch unconditionally, so a reopened worktree-active issue re-provisions through the existing path [source: web/api/worktree.py:39-63] [source: web/api/tests/test_worktree.py].

## Continuity model: session resume over a re-feed floor

> **Superseded 2026-06-14 — Session Resume shipped.** The original framing below ("pi is one-shot, so there is no session to resume") is **no longer true**: pi now dispatches via `pi --mode rpc` with persistent sessions, and Session Resume is **live** on the in_review/blocked reply loop for every binding (ADR-0009 + ADR-0010 accepted; #050/#051 landed, all bindings on `pi_mode: rpc`). On a resume Run only the newest operator-reply delta is injected — the curated blobs are not re-fed. **Re-feed remains the guaranteed floor** for resume-ineligible runs (agent/cwd/SHA change, missing session), so the paragraph below still describes that fallback path. See [Session Resume continuity](session-resume-continuity.md).

Historical (now the re-feed floor, not the only mode): pi was invoked one-shot (`--no-session`) with no session to resume; continuity came from re-feeding `comments_md` (operator-curated thread) + `context_md` (agent-owned cumulative log) into every Podium prompt, and a fresh run re-read both. That re-feed is now the fallback beneath Session Resume. [source: prompt_renderer.py] [source: agent_runner.py]

> **Role reframe (2026-06-13, grill-me, C-0179):** post-Resume the surfaces keep this re-feed behavior on the floor but their *primary* roles shift. Issue Comments is no longer "the continuity mechanism" — the agent never consumes the Comments blob as memory; on resume only the newest operator-reply delta is injected, and the full blob is re-injected solely on the re-feed floor. Issue Context becomes "floor substrate + UI observability," not the primary memory (the native session is). Live **Steering** (ADR-0010) appends to Comments as a distinct entry. The data model and injection plan (#049/#050) are unchanged — this is terminology only. See `CONTEXT.md` (Issue Comments / Issue Context / Steering) and the ADR-0009 "Resolved 2026-06-13" amendment.

## Prompt-renderer directive

`render_previous_comments_block` gained `flag_operator_replies` (Podium path only); when set it appends a directive elevating the most-recent `### Operator Reply` block to "the operator's current request" while keeping other comment text untrusted. See [Prompt renderer](prompt-renderer.md#escaping-and-context-blocks).

## Frontend

`web/frontend/lib/api.ts` adds `postReply(id, body)`. `IssueFlyout.tsx` renders a `ReplyComposer` at the top of the comments tab, above the chronological comment thread. Send is gated via `isActiveRunState`: disabled with a hint when the issue is `running`/active-run ("Agent is running — reply when it parks for review.") or `todo` ("Already queued to run."), and on empty draft. On success it clears the draft, invalidates `["issue", id]` + `["issues", binding_name]`, and calls the flyout close callback so the panel closes after a successful operator reply; failed sends do not close because the close is wired only through the mutation `onSuccess` path. The e2e reply spec asserts the successful send closes the flyout and the card moves to Todo [source: web/frontend/components/IssueFlyout.tsx] [source: web/frontend/tests/reply.spec.ts].

## Untrusted-content trade-off

The comments block warns the agent not to treat comment text as system instructions, yet operator replies *are* trusted directives. Resolution: single-operator authenticated console (shared-password auth, #018) — the renderer elevates the most-recent `### Operator Reply` header to "the current request" while still telling the agent not to execute instructions embedded inside other/quoted comment text. Attribution uses a generic "Operator" label + timestamp; no per-user identity is tracked [source: plans/feature-operator-reply-comments.md].

## The `/comment` sibling (ADR-0017)

`POST /api/issues/{id}/comment` (`comment_on_issue`, landed 2026-06-20) is the append-only **Comment** primitive that `/reply` is the reopen variant of. It mirrors `/reply`'s append + monotonic `updated_at` bump + `issue.updated` publish, reuses the same `ReplyCreate` body validation (422 empty / 400 unknown key / 404 unknown id), but **drops the three reopen-coupled effects**: no `state='todo'` flip, no `state IN (...) AND latest_run_state NOT IN (...)` guard (so it works in **any** state — including `running` — and **never 409s** on state grounds), and no wake-sentinel touch (no re-dispatch). ADR-0017 originally appended the body **verbatim** with no injected header. Issue-chat B1 changed attribution only: the API now wraps the operator-owned body with `_stamp_comment("operator", ...)` before the same server-side concatenation. The no-flip, no-state-gate, and no-wake behavior is unchanged, and no migration rewrites legacy blobs [source: web/api/main.py] [source: web/api/tests/test_comment.py] [source: docs/handoffs/2026-07-21-018-podium-issue-chat-spec.md].

This is the durable fix for the C-0281 patrol re-dispatch churn: Temporal patrols repointed `add_comment` from `/reply` to `/comment` and stamp their own `### Patrol (<iso-ts>)` header, so a patrol comment no longer reopens the issue. Reopen-on-fail / close-on-pass stay owned by the patrol's **explicit** `update_issue(state=…)` calls, decoupling *appending a comment* from *reopening for re-dispatch* [source: automation/homelab-stack/src/homelab_router/podium_adapter.py] [source: wiki/analyses/adr-0015-patrol-podium-tracker-adapter.md]. A future operator "Note" action would post through `/comment` the same way (deferred, YAGNI). The frontend splits a `### Patrol (` block as its own always-shown comment entry [source: web/frontend/components/IssueFlyout.tsx].

## Related

- [Prompt renderer](prompt-renderer.md)
- [Podium tracker](podium-tracker.md)
- [Scheduler loop](scheduler-loop.md)
- [ADR-0015 patrol Podium tracker adapter](../analyses/adr-0015-patrol-podium-tracker-adapter.md) — the patrol-side `/comment` repoint and the C-0279–C-0281→ADR-0017 arc.
