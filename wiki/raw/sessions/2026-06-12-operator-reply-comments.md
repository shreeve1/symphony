# Session Capture: Operator reply comments — reply-in-flyout that continues the AI conversation

- Date: 2026-06-12
- Purpose: Implemented the operator-reply feature (`/dev-build` of `plans/feature-operator-reply-comments.md`), closing the gap between the bidirectional Issue Comments intent and the prior implementation, which had no structured operator-write path and no link between a comment and re-dispatch.
- Scope: Durable architecture/contract facts about the new reply endpoint, the prompt-renderer operator-reply directive, and the transcript-re-feed continuity model. Excludes routine build chatter and per-wave audit mechanics.

## Durable Facts

- A new endpoint `POST /api/issues/{issue_id}/reply` accepts `{ "body": str }`. On an issue in `in_review`/`blocked`/`done` whose `latest_run_state` is not `queued`/`running`, it appends an attributed `### Operator Reply (<ISO-timestamp>)` block to `comments_md` AND flips `state` to `todo` AND bumps `updated_at`, all in one atomic conditional SQL `UPDATE` (`comments_md = COALESCE(comments_md,'') || ?`), then publishes an `issue.updated` WebSocket event and returns the updated row. — Evidence: `web/api/main.py` (`reply_to_issue`), `web/api/tests/test_reply.py`
- The `todo` state-flip is the re-dispatch mechanism: posting a reply is the operator action that makes the next scheduler tick pick the issue up and re-run the agent. The endpoint only sets `todo`; re-dispatch then obeys the binding's existing approval/schedule gates — no second dispatch path is introduced. — Evidence: `web/api/main.py`, `tracker_podium.py` (candidate scan)
- Guard semantics: `running`/`todo` issue state → 409; any allowed state with active `latest_run_state` (`queued`/`running`) → 409; empty/whitespace body → 422; unknown extra key → 400; unknown issue id → 404. The append + state flip is a single atomic conditional `UPDATE` with `rowcount` disambiguated into 404 (gone) vs 409 (guard failed) by a follow-up `SELECT` — no client/Python read-modify-write race. — Evidence: `web/api/main.py`, `web/api/tests/test_reply.py`
- `COALESCE(comments_md,'')` guards a legacy/direct-write row where `comments_md` is `NULL`; SQLite's `NULL || text` yields `NULL`, which would silently drop the reply while still flipping state. — Evidence: `web/api/main.py`, `web/api/tests/test_reply.py::test_reply_on_null_comments_md`
- `prompt_renderer.render_previous_comments_block` gained a keyword-only `flag_operator_replies: bool = False`. When `True` it appends, after the existing untrusted-context caveat, a directive that blocks headed `### Operator Reply` are the operator's directives and the most recent one is the current request to act on, while text inside other comments stays untrusted. `render_prompt` passes `flag_operator_replies=True` only on the `tracker_kind == "podium"` branch; the Plane path is byte-for-byte unchanged. — Evidence: `prompt_renderer.py`, `tests/test_prompt_renderer_podium.py`
- Continuity model is transcript re-feed, not pi session resume: pi is invoked one-shot (`--no-session`), so there is no session to resume. Continuity comes from re-feeding `comments_md` + `context_md` into every Podium prompt. — Evidence: `agent_runner.py`, `prompt_renderer.py`, `CONTEXT.md:24,75`
- Done-reopen needs no new code: a reply on a `done` issue silently reopens it (→ `todo`); `create_worktree` (`web/api/worktree.py:39-63`) already reuses an orphan branch unconditionally (gated only on worktree dir presence + branch-ref existence, not issue state), so a reopened worktree-active issue re-provisions through the existing path. — Evidence: `web/api/worktree.py`, `web/api/tests/test_worktree.py::test_create_worktree_reuses_existing_branch`
- No schema change/migration: the endpoint touches only existing `comments_md`, `state`, `updated_at` columns and reuses the existing five issue states. — Evidence: `web/api/main.py`, `web/api/schema.py`

## Decisions

- Auto-dispatch on post (one operator action continues the thread) rather than a separate "re-run" affordance. — Evidence: this session capture, `plans/feature-operator-reply-comments.md` (Solution Approach)
- Untrusted-content trade-off: the renderer elevates the most-recent `### Operator Reply` header to "the current request" while still telling the agent not to execute instructions embedded in other/quoted comment text. Justified by the single-operator authenticated console (shared-password auth, #018); attribution uses a generic "Operator" label + timestamp, no per-user identity. — Evidence: `plans/feature-operator-reply-comments.md` (Notes), `prompt_renderer.py`
- The raw-blob `MarkdownEditor` is kept intact alongside the new `ReplyComposer`; operators may still freely restructure the thread. — Evidence: `web/frontend/components/IssueFlyout.tsx`

## Evidence

- `web/api/main.py` — `ReplyCreate` model, `ALLOWED_REPLY_STATES`/`ACTIVE_RUN_STATES` constants, `reply_to_issue` endpoint, and the `ctx`-strip fix so the 422 whitespace-body case (custom `field_validator` `ValueError`) JSON-encodes.
- `prompt_renderer.py` — `flag_operator_replies` param + Podium-only call site.
- `web/frontend/lib/api.ts` — `postReply(id, body)`; `web/frontend/components/IssueFlyout.tsx` — `ReplyComposer` (run-state-gated send, disabled hint, transient error, query invalidation).
- `web/api/tests/test_reply.py`, `tests/test_prompt_renderer_podium.py`, `web/frontend/tests/reply.spec.ts` — coverage.

## Exclusions

- No secrets, `/home/james/symphony-host.env` values, or transcript captured.
- Per-wave `/dev-build` pi-audit mechanics and one flaky `tests/test_podium_sqlite_concurrent.py` (passes in isolation; fails only under concurrent CPU/SQLite contention) recorded only as build-process detail, not durable knowledge.

## Open Questions And Follow-Ups

- Optional follow-up: surface operator-reply semantics in each binding's `WORKFLOW.md` (homelab/trading repos). The renderer directive alone is sufficient; this is not required.
- Out of scope (explicitly not built): mid-run reply queuing, multi-reply batching with a single trigger, per-comment table/threading.
