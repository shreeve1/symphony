---
title: "ADR-0022 — Post the agent's captured turn, not a forced summary block"
type: analysis
status: promoted
created: 2026-06-23
updated: 2026-06-26
sources:
  - docs/adr/0022-post-the-agents-captured-turn-not-a-forced-summary.md
  - plans/adr-0022-post-captured-turn.md
  - claude_runner.py
  - prompt_renderer.py
  - scheduler/__init__.py
  - scheduler/markers.py
  - scheduler/sanitize.py
  - tests/test_captured_turn.py
confidence: high
tags: [adr, output-contract, comments, summary, pi-rpc, claude, assistant-turn, accepted]
---

# ADR-0022 — Post the agent's captured turn, not a forced summary block

**Status: `accepted`** — implemented 2026-06-26 per [implementation plan](../../plans/adr-0022-post-captured-turn.md).

## Problem (dotfiles Issue #105 / Run #310)

The operator asked the agent "give me a prompt I can use to migrate/reconcile a wiki." The closing comment *described* the prompt — "Delivered a reusable operator prompt… returned inline" — but the prompt text was absent. Root cause is structural, not a flake: the **only** channel from agent to Podium comments is the `SYMPHONY_SUMMARY_BEGIN/END` block, and the injected `OUTPUT_CONTRACT` frames that block as a status recap ("what you did, what you found", `prompt_renderer.py:44`). When the deliverable *is* text, the agent narrates it in the summary and emits the real artifact only in its conversational turn — which Symphony never reads. For Claude this is explicit: the agent is told to write its "full final output" to a result file (`claude_runner.py:1319`); pane chatter is discarded [source: docs/adr/0022-post-the-agents-captured-turn-not-a-forced-summary.md].

## Key finding — the engine already captures the natural turn

- **pi:** `_drain_rpc_events` accumulates every streamed assistant `text_delta` into `assistant_parts`; `run_pi_rpc_agent` returns `"".join(assistant_parts)` as stdout (`agent_runner.py:727,781`) — the same stream ADR-0019 Thread B spools for remote tailing. The scheduler then discards it by sub-extracting only the `SYMPHONY_SUMMARY` block via `_extract_summary` [source: agent_runner.py].
- **claude:** the full assistant turn lives in the on-disk transcript JSONL that session-resume and the Live Session Tail already read.

So "what the agent actually said" is in hand for both runners; it is thrown away in favor of a self-summary [source: docs/adr/0022-post-the-agents-captured-turn-not-a-forced-summary.md].

## Decision

Post the captured natural turn as the comment; stop forcing a self-authored summary. One model for both runners:

- Agent answers naturally and emits one terminal `SYMPHONY_RESULT:` marker (or `SYMPHONY_QUESTION` / `SYMPHONY_SCHEDULE`). The `SYMPHONY_SUMMARY` block becomes **optional**, kept only as a fallback when a turn can't be captured.
- Engine posts the captured turn — pi: `drain.assistant_parts`; claude: last assistant turn from the transcript (text blocks since the last operator input, `tool_use`/`tool_result` stripped) — through the **existing secret redaction** (non-negotiable trust boundary).
- Verdict/approval/schedule markers keep parsing from the raw `result.stdout`/`stderr` streams (the C-0257 path), so classification is untouched. Completion signals unchanged: done-file (claude), `agent_end` (pi) — completion is **not** inferred from idle-at-prompt (the historical hang path).

**Bounds decoupled** (the old single ~4000 cap did two jobs): a **generous display bound** (~12000, file-fallback above for coding bindings — write artifact to file, commit, post path + excerpt) so the operator sees the whole artifact; a **hard tail-cap on re-injection** when that comment is fed back as untrusted prior context (`comments_md`, capped 12000), preserving the guard #046 built the 4000 bound for.

## Considered alternatives

- **Wording-only fix to `OUTPUT_CONTRACT` ("A").** Rejected as primary fix — a soft crutch; the agent still chooses to obey and still compresses its answer. We already capture the real turn; routing it is strictly more robust. (The wording is still updated to match the new model.)
- **Additive capture ("C-additive").** Keep the summary contract *and* also post the turn. Rejected — two channels, double the noise, failure mode not removed.
- **Fully bare, no done-file (claude).** Completion inferred from idle-at-prompt. Rejected — that is exactly the fragile path that produced the old "Agent timed out" hangs; the done-file is invisible overhead, not content.

## Consequences

- Noisier comments, accepted deliberately — fidelity over #046's spotless stream.
- **Partially supersedes ADR-0007 / #046:** the curated clean-comment-stream rationale and verbatim-summary posting (C-0160 sub-extract, C-0161 verbatim post) are walked back; the marker contract, secret redaction, and re-injection cap survive. #046's other wins (no Timeline footer, no claim comment, raw-stream verdict parsing) are unaffected [source: wiki/analyses/podium-046-unified-output-contract.md].
- pi and claude converge on one delivery model; the earlier "A for pi, C for claude" split is dropped once pi was found to already capture the turn.
- **Related but separate:** defaulting `claude_persist: true` for local bindings (`config.py:101`) was discussed alongside this — it does *not* fix this bug (output flows identically warm or cold) and carries its own soak (8-slot cap, 45-min TTL); remote stays excluded by config (ADR-0012). Tracked as its own change, foldable into the same deploy.

## Related

- [ADR-0019 — orchestrator owns agent I/O](adr-0019-orchestrator-owns-agent-io.md)
- [#046 unified output contract](podium-046-unified-output-contract.md)
- [Prompt renderer](../concepts/prompt-renderer.md)
- [ADR-0013 — warm Claude + send-keys steer](adr-0013-warm-claude-and-send-keys-steer.md) (claude_persist)
