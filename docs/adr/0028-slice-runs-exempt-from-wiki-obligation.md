---
status: accepted
---

# ADR-0028 — Podium slice runs are exempt from the per-task wiki obligation

## Context

`CLAUDE.md` makes the wiki a "standing obligation": every agent runs `/wiki-update` before reporting a task done. Every dispatched Podium slice reads `CLAUDE.md` as its agent context and dutifully runs `/wiki-update` **inside its run, before land**, committing bookkeeping (`CLAIMS.md`, `log.md`, `ROUTING.md`, `index.md`, `analyses/…`) onto its own branch. These files are append-heavy and touched by *every* slice, so N parallel slices from the same parent deterministically diverge and the FF-only land rebase (`web/api/worktree.py:238`) conflicts on wiki content — recurred on #134 and #136 (C-0335). Beyond the collision, N independent appenders cannot dedupe each other, allocate claim IDs serially, or see whether the batch contradicts an ADR — so the wiki grows unbounded and drifts from the ADRs.

A `locks: [wiki]` reservation is the wrong tool: because *every* slice wiki-updates, locking `wiki` would serialize all slices and destroy parallelism. Excluding `wiki/` from the land rebase is also wrong: dropping the commits loses knowledge, and union-merging silently concatenates claim rows — reintroducing the C-0327/C-0328 duplicate-ID class.

## Decision

**Podium slice runs (any dispatched issue run) are exempt from the per-task wiki obligation.** A slice captures its "why" in the issue comment (ADR-0022, "post the agent's captured turn") and does nothing to the wiki. Wiki capture becomes a **single consolidated `/wiki-update` pass run after a batch of slices lands**, on `main`, by a single writer.

- **Scope: broad.** The exemption applies to *any* dispatched slice, including a slice running solo — not only parallel/dependency-grouped slices. "Sometimes slices write the wiki" is harder to reason about than "slices never do," and a solo slice that wrote the wiki would establish a convention the next parallel batch collides with.
- **Trigger: operator-driven.** The consolidated pass is a deliberate operator action (as run at the end of the 2026-06-25 session covering #133–#137), not an automatic lander step. Deciding *which* batch is "done enough" to document needs judgment that fits an operator, not a trigger.
- The per-task obligation **still applies to interactive sessions** — it was only ever wrong for slices, which are mid-pipeline, not at a session boundary, so "before reporting done" was the wrong trigger for them.

A single consolidated pass on main fixes all three failure modes by construction: one writer → no parallel divergence; one reasoning pass over the whole landed batch → serial claim-ID allocation, dedup, supersession marking, **and ADR coherence updates alongside the claims**; bounded growth → the pass decides what is durable across the batch instead of N agents each appending "what I did."

## Considered alternatives

- **Per-slice staging + post-land replay (a1).** Slices stage a wiki delta; a post-land step replays deltas onto main. Rejected: the replay cannot be mechanical — serial claim-ID allocation, dedup, supersession, and ADR coherence all require an LLM reasoning pass, so the staging machinery buys nothing and the hard part just moves. It degenerates into the consolidated pass with extra plumbing.
- **Exclude `wiki/` from land rebase.** Rejected — loses knowledge or reintroduces duplicate-ID corruption (see Context).

## Consequences

- A slice agent's fresh in-context "why" is not written to the wiki at land time. It is **not lost**: ADR-0022 already posts the agent's captured turn to the issue thread, which the consolidated pass reads to reconstruct intent.
- **Forgotten-pass risk + mitigation (dev-review, 2026-06-25):** the broad exemption means *no* wiki capture happens during dispatch, so if the operator merges a batch and never runs the consolidated `/wiki-update`, the slices' durable knowledge survives only in ephemeral issue comments. Mitigation: the land-finalizer emits a **"wiki pass needed"** marker when it lands slices (mirroring the existing `ralph-merge-needed` pattern), so a forgotten consolidated pass is visible rather than silent. This is the one hole the exemption opens and the marker closes it cheaply.
- No Symphony code change: the orchestrator never invoked `/wiki-update`; it renders the prompt and lands the branch. The cause was the `CLAUDE.md` rule, so the fix lives there.
- A future reader who sees slices not updating the wiki will wonder why — this ADR is the answer.
