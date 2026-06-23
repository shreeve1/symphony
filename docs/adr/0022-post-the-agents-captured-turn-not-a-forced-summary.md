# Post the agent's captured turn, not a forced summary block

Status: **proposed** (design locked in a grilling session 2026-06-23; not yet built)

## Context

ADR-0007 / Issue #046 established a single engine-owned output contract: the
agent ends every run by emitting `SYMPHONY_RESULT: done|review|blocked` (or a
`SYMPHONY_QUESTION` / `SYMPHONY_SCHEDULE` marker) **plus a hand-authored
`SYMPHONY_SUMMARY_BEGIN`/`SYMPHONY_SUMMARY_END` block**. The scheduler extracts
*only* that block (`_extract_summary`), redacts it, bounds it to ~4000 chars, and
posts it verbatim as the issue comment. The explicit goal was a clean, noise-free
comment stream — no transcript, no tool spam.

That contract conflates two jobs into one channel, and the second job quietly
breaks the first:

1. **Machine signalling** — the terminal verdict marker the scheduler classifies
   on. Small, load-bearing, works.
2. **Content delivery** — the human-readable comment. Forcing this through a
   *self-summary* makes the agent compress, and worse, makes it treat the block
   as a status recap rather than the delivery envelope.

dotfiles Issue #105 / Run #310 exposed the failure cleanly. The operator asked
"give me a prompt I can use to migrate/reconcile a wiki." The agent produced the
prompt in its conversational turn, then wrote a work-recap to its summary block
that said *"Delivered a reusable operator prompt… returned inline."* The prompt
itself never reached the comment — because the agent's natural turn is **not** a
channel Symphony reads. For the Claude path this is explicit: `claude_runner`
tells the agent to write its "full final output" to a result file
(`claude_runner.py:1319`); whatever it typed in the tmux pane is discarded. So
the operator got a description of the artifact, not the artifact.

The diagnosis: the `OUTPUT_CONTRACT` framing ("the summary block carries your
natural end-of-turn message — what you did, what you found",
`prompt_renderer.py:44`) reads as "write a status report," and it is the *only*
surface the operator sees. When the deliverable *is* text, the agent narrates it
instead of inlining it, and the real answer evaporates.

A key fact surfaced during grilling: **the engine already captures what the agent
actually said.** For pi, `_drain_rpc_events` accumulates every streamed assistant
`text_delta` into `assistant_parts`, and `run_pi_rpc_agent` returns
`"".join(assistant_parts)` as stdout (`agent_runner.py:727,781`) — the same
stream ADR-0019 Thread B spools for remote tailing. For Claude, the full
assistant turn lives in the on-disk transcript JSONL that session-resume and the
Live Session Tail already read. In both cases the natural turn is in hand; the
scheduler then throws it away by sub-extracting only the `SYMPHONY_SUMMARY` block.

## Decision

**Post what the agent actually said. Stop forcing a self-authored summary.** This
is ADR-0019's "the orchestrator owns the agent's I/O" applied to the return path:
the orchestrator surfaces the agent's real turn rather than demanding the agent
curate one for it.

One output model for both runners:

- The agent answers naturally and emits one terminal `SYMPHONY_RESULT:` marker
  line (or `SYMPHONY_QUESTION` / `SYMPHONY_SCHEDULE`). The `SYMPHONY_SUMMARY`
  block becomes **optional** — retained only as a fallback when a turn can't be
  captured.
- The engine posts the **captured natural turn** as the comment:
  - **pi** — `drain.assistant_parts` (already captured; the scheduler simply
    stops sub-extracting the summary block).
  - **claude** — the last assistant turn from the transcript JSONL: text blocks
    since the last operator input, with `tool_use`/`tool_result` blocks stripped.
- Always through the **existing secret redaction** before posting — this is a
  trust boundary and is non-negotiable on the new path.
- The terminal verdict/approval/schedule markers keep parsing from the raw
  `result.stdout`/`stderr` streams (the C-0257 path), so verdict classification is
  untouched. Completion signals are unchanged: the done-file (Claude) and the
  `agent_end` event (pi) remain the robust "turn finished" signals — we are *not*
  inferring completion from idle-at-prompt, which historically hung runs.

**Bounds are decoupled** (the old single ~4000 cap did two jobs):

- **Display bound** — what lands in the comment for the operator to read: generous
  (~12000), with a file-fallback above that for coding bindings (write the artifact
  to a file, commit it, post the path + an excerpt). You see the whole artifact.
- **Re-injection bound** — when that comment is later fed back as untrusted prior
  context (`comments_md`, capped at 12000), keep the hard tail-cap. This preserves
  the guard #046 built the 4000 bound for: a runaway turn can't smuggle a giant
  blob into the next prompt.

## Considered alternatives

- **Wording-only fix to `OUTPUT_CONTRACT` ("A").** Tell the agent the summary
  block is the sole operator-facing surface, so inline artifacts verbatim instead
  of describing them. Rejected as the *primary* fix: it's a soft crutch — the
  agent still chooses whether to obey, and it leaves the agent compressing its
  real answer into a recap. We already capture the true turn; routing that is
  strictly more robust than asking the agent to duplicate it. (The wording will
  still be updated to match the new model: "answer naturally; no summary block
  required.")
- **Additive capture ("C-additive").** Keep the result-file/summary contract *and*
  also post the captured turn. Rejected: two channels, double the noise, and it
  doesn't remove the failure mode — it just adds a second comment.
- **Fully bare, no done-file (claude).** Purest CLI feel, completion inferred from
  idle-at-prompt. Rejected: idle detection off a tmux pane is exactly the fragile
  path that produced the old "Agent timed out" hangs. The done-file is invisible
  protocol overhead, not content, so keeping it costs nothing.

## Consequences

- **Noisier comments, accepted deliberately.** A natural turn carries more than a
  curated summary — narration, intermediate reasoning. This is the trade we are
  choosing: fidelity over the spotless stream #046 optimized for.
- **Partially supersedes ADR-0007 / #046.** The clean-comment-stream rationale and
  the verbatim-summary posting are walked back; the marker contract,
  secret-redaction, and re-injection cap survive. #046's other wins (no Timeline
  footer, no claim comment, raw-stream verdict parsing) are unaffected.
- **pi and claude converge** on one delivery model; the earlier "A for pi, C for
  claude" split is dropped once we found pi already captures the turn.
- **Related but separate:** defaulting `claude_persist: true` for local bindings
  (`config.py:101`) was discussed alongside this and is its own change — it does
  not fix this bug (output flows the same way warm or cold) and carries its own
  soak (8-slot cap, 45-min TTL); remote stays excluded by config (ADR-0012).
- Known ceiling: "last assistant turn" extraction for Claude depends on transcript
  shape; the retained summary-block fallback covers a turn that can't be cleanly
  isolated.
