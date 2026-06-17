---
id: 052
title: Question Park — agent may park to ask the operator
status: done
blocked_by: [050, 051]
parent: null
priority: 0
created: 2026-06-13
updated: 2026-06-13
actor: ralph
---

## What to build

Reverse Symphony's unattended "never ask" contract so the agent may deliberately end a turn to ask the operator a clarifying question, then resume its session with the answer once the operator replies.

> **ADR-0010 note:** the pi side now runs through the RPC adapter (#050), so the `SYMPHONY_QUESTION` marker is parsed from the RPC final assistant text (`AgentResult.stdout` at `agent_end`) — same marker contract as Claude, no protocol change needed here. The richer RPC `extension_ui_request` ask-path is deferred; the marker contract gives uniform park behaviour across both agents and is the minimal change. This is **park-and-reply turn-taking between Runs**, distinct from live mid-run **Steering** (#056), which is pi-only.

- Update the prompt wrappers (`claude_runner._wrap_prompt` + the Pi equivalent) to permit a Question Park as a legitimate turn outcome instead of forbidding questions outright. The agent may still complete or report blocked-on-error as before.
- Introduce a new completion signal `SYMPHONY_QUESTION` that the output contract parses, three-way distinguishing: completed (existing `SYMPHONY_RESULT`/summary), **question-park** (new), and blocked-on-error (existing). The question text is carried in the marker block.
- Lifecycle mapping: a Question Park parks the issue to **`in_review`** (a deliberate consult, not impeded — `in_review` already re-dispatches on operator reply per the operator-reply path), posting the agent's question as its summary/comment so the operator sees what is being asked.
- The operator's reply re-dispatches and, via #050/#051, **resumes the session** so the agent receives the answer with full prior context intact.

This is the turn-taking backbone; it is only useful because resume preserves the thread across the question (hence the dependency on #050/#051).

## Acceptance criteria

- [x] Output-contract parser recognizes three outcomes: completed, question-park (`SYMPHONY_QUESTION`), blocked-on-error — with the question text extracted from the marker.
- [x] A question-park outcome transitions the issue to `in_review` and records the question as the run's posted summary/comment.
- [x] The prompt wrappers no longer forbid questions; they describe the Question Park protocol for both Pi and Claude.
- [x] An operator reply to a question-parked issue re-dispatches and resumes the session (predicate-pass path), delivering the answer via the delta-only prompt.
- [x] A blocked-on-error outcome still maps to `blocked` (unchanged), distinct from question-park.

## Verification

`uv run pytest tests/test_scheduler*.py tests/test_prompt_renderer*.py web/api/tests/test_reply.py -q`

## Blocked by

- Blocked by #050, #051

## Implementation Notes

Added `SYMPHONY_QUESTION_BEGIN` / `SYMPHONY_QUESTION_END` to the shared output contract and scheduler parsing. Question-park Runs now finish successfully with verdict `question`, post `**Symphony question:**` as the issue comment, and transition the issue to `in_review` so the existing operator-reply redispatch/resume path can carry the answer back into the preserved session. Claude's tmux wrapper now permits the question-park protocol instead of forbidding questions; Pi receives the same protocol through the shared rendered prompt. The blocked-result path remains unchanged.
