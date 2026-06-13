# Handoff — grill-me: should Issue Comments and Issue Context be reworked given Session Resume + pi-RPC?

**For:** a `/grill-me` session.
**Date created:** 2026-06-13.
**Operator goal (verbatim intent):** "Before I perform any work, I want to address the Comments and Context sections. I'm wondering if these should be reworked." The operator wants to talk out whether the two per-Issue memory surfaces — **Issue Comments** and **Issue Context** — still have the right shape now that Symphony is committing to native CLI **Session Resume** (ADR-0009) and **pi-RPC live Steering** (ADR-0010). This is a design/terminology grill, not an implementation task.

> Grill discipline: do not assume the answer is "rework them." The real question is what each memory surface is *for* once the agent's own session holds the verbatim conversation. Resolve the design tree one branch at a time, recommend an answer per question, cross-check against the code, and update `CONTEXT.md` / ADRs inline as decisions crystallise. Treat "drop Issue Context" and "keep everything as-is" as equally live hypotheses until tested.

---

## What was recently decided (review first)

Read these before grilling — they reframe the whole Comments/Context question:

- **ADR-0009 (`accepted`, partially implemented) — Session Resume continuity.** Continue a parked Issue by resuming the agent's own on-disk CLI session, best-effort, layered over the stateless **re-feed floor** which stays the guarantee. On a resume Run the prompt collapses to **delta-only** (newest operator-reply block + mechanical wrapper) — the Issue body, full Comments, full Context, and WORKFLOW.md are **omitted** because the session already holds them. Symphony keeps *writing* `comments_md`/`context_md` (for the UI and the fallback floor) but stops *injecting* them on resume, and **skips #026 compaction on resume Runs**. Backlog: `.kanban/047`–`055`; #047 (run columns) + #048 (decision core) landed.
- **ADR-0010 (`proposed`, parity spike PASSED) — dispatch pi via RPC for live Steering.** pi pivots to `pi --mode rpc`; the native RPC session holds verbatim history and exposes `compact`/`set_auto_compaction` + compaction events. Live mid-run **Steering** (RPC `steer`, pi-only) is added as a *third* operator input path alongside the between-Run reply loop. Claude stays tmux park-and-reply. #050 re-sequenced onto RPC; #056/#057/#058 added.
- **Net effect on memory:** there are now potentially **three** representations of an Issue's history — the agent's **native session** (verbatim conversation, the resume substrate), **Issue Context** (agent-curated cumulative *summary*), and **Issue Comments** (operator thread). Before ADR-0009, Comments+Context *were* the continuity mechanism (re-fed every Run). After it, on the resume path they are neither read nor injected — their role has quietly shifted from "the memory" to "the floor + the record + the UI." That shift is what this grill must make explicit.

### Issue states this intersects
- `.kanban/047`,`048` done; `049`–`055` pending; `056`/`057`/`058` (RPC steer/UI/lifecycle) pending. None committed beyond #047/#048. No loop running.

---

## Grounded facts (verified this session)

**Issue Comments (`comments_md`)** — `CONTEXT.md` "Issue Comments"; `wiki/concepts/operator-reply.md`:
- Bidirectional operator/AI thread, one markdown blob per Issue. Operator may freely edit/delete/restructure. AI writes are append-only (a summary after each Run).
- Operator reply appends `\n\n### Operator Reply (<ISO>)\n\n<body>` and flips state to `todo` in a single atomic SQL `comments_md = COALESCE(comments_md,'') || ?` update (`web/api/main.py`).
- Re-fed into every prompt with `flag_operator_replies=True` (`prompt_renderer.py:219`).

**Issue Context (`context_md`)** — `CONTEXT.md` "Issue Context":
- The agent's *own* per-Issue session log; agent reads at Run start, writes full Run output at completion. Operator can view but normally doesn't write. Rendered as a context block (`prompt_renderer.py:223`).
- Engine-compacted before dispatch when it exceeds a per-binding token threshold (#026, `_maybe_compact_context`, `scheduler.py:523-589`): the engine invokes the agent with a Symphony-owned compaction prompt that rewrites old entries to a summary while keeping the most recent N Runs verbatim.

**The native session (new substrate)**:
- ADR-0009: keyed by `derive_session_id(issue.id)` = `UUIDv5`; namespaced by cwd; holds the verbatim conversation. Resume sends delta-only.
- ADR-0010: `pi --mode rpc --session-id <derived>` persists the same jsonl; RPC has native `compact` + `set_auto_compaction` + `compaction_start/end` events.

**The collision ADR-0009 explicitly deferred:** "letting native session auto-compaction replace #026 was deferred, not adopted — the engine compaction and the native transcript are two context stores whose reconciliation is a separate, thornier decision." That deferred decision is now squarely in scope for this grill.

---

## Design tree the grill must resolve (suggested order)

1. **Does Issue Context still earn its place?** With the native session holding verbatim history (resume + RPC), the agent-curated cumulative *summary* (`context_md`) overlaps it. Options: (a) keep as the re-feed floor + UI summary only; (b) demote to UI-only (stop injecting even on re-feed, trust the session); (c) drop entirely and rely on session + Comments. What is Context *for* once it is not the primary memory?
2. **Engine compaction (#026) vs native auto-compaction.** RPC pi can self-compact (`set_auto_compaction`, `compact`). Do we drop the engine compaction step for RPC pi (let the session manage its own context window) and keep #026 only for the re-feed floor / non-RPC / Claude? Or keep engine compaction as the authority over `context_md` regardless? Beware two compactors fighting over two stores.
3. **What is Issue Comments for, post-resume?** Its continuity-injection role fades (resume sends only the delta reply). Confirm Comments = operator I/O + human-readable record + UI thread, *not* a memory the agent depends on. Does anything break if Comments is no longer re-fed verbatim on the resume path (it already isn't)?
4. **Where do live Steering messages land?** Steering (ADR-0010) is a new mid-run operator input not captured by either surface today. Should a steer append to Comments (so the thread is a faithful record of everything the operator told the agent, mid-run included)? Ephemeral? A new sub-thread? This is a genuinely new write-path question.
5. **Source-of-truth map.** Define, as a table: native session (verbatim, agent-owned, resume substrate), Issue Context (curated summary — owner? still written every Run?), Issue Comments (operator thread). For each: who writes, who reads, what is injected on re-feed vs resume vs steer, and which is authoritative when they disagree.
6. **Question Park / ask-me answers.** Operator replies to a parked question via Comments (append + flip), delta-fed on resume. Confirm this stays consistent and that the answer is recorded where the operator expects.
7. **Terminology.** If the roles shift, `CONTEXT.md`'s "Issue Comments" and "Issue Context" definitions (and their `_Avoid_` notes) need rewording from "continuity mechanism" to their new roles. Possibly a new relationship line about the native session as a distinct, non-curated store.

## Alternatives to test the hypothesis against (don't skip)
- **Keep both exactly as designed** (the ADR-0009 stance: write both, inject on re-feed, omit on resume). Is the "redundancy" actually a cost, or is the floor worth the duplication? Re-feed *must* keep working when resume fails.
- **Collapse Context into the session** — stop maintaining `context_md` as a separate curated store; derive any UI summary on demand from the session jsonl. Removes a store and #026, but loses the floor's independence from disk-session availability.
- **Keep Context, drop engine compaction** — let the agent self-summarise into `context_md` (or let the native session auto-compact) and retire #026. Fewer engine moving parts; relies on agent discipline.
- **Comments as the single operator-facing log; Context invisible** — Context becomes a pure engine/agent internal, never surfaced, Comments is the only thing the operator reads/writes.

---

## Pointers
- Code: `prompt_renderer.py` (`comments_md`/`context_md` rendering, `render_issue_context_block`, operator-reply flagging, `OUTPUT_CONTRACT`), `scheduler.py` (`_maybe_compact_context:523`, re-feed vs resume dispatch), `web/api/main.py` (reply append + state flip), `context_compaction.py` (#026), `session_continuity.py` (#048 resume decision core), `agent_runner.py` / `claude_runner.py` (dispatch).
- CONTEXT.md terms: **Issue Comments**, **Issue Context**, **Continuity**, **Session Resume**, **Question Park**, **Session Tail**, **Steering** (new, ADR-0010).
- ADRs: `0006-engine-state-surfaced-by-polling-not-websocket.md`, `0009-session-resume-continuity.md`, `0010-pi-rpc-dispatch-for-live-steering.md`. (Reworking Comments/Context may warrant a new ADR or an ADR-0009 amendment.)
- Wiki: `concepts/session-resume-continuity.md`, `concepts/operator-reply.md`, `analyses/adr-0009-...`, `analyses/adr-0010-...`, `analyses/podium-026-context-compaction.md`. Claims `C-0175`–`C-0178`.
- Backlog: `.kanban/issues/047`–`058`. The Comments/Context rework, if pursued, likely re-touches #049 (delta-only renderer), #050 (RPC resume), and #026's role.

## State at handoff
- Session Resume (ADR-0009) + RPC pivot (ADR-0010) are design-stage; only #047/#048 are implemented. Live behaviour is still pure re-feed + pi one-shot. Comments/Context behave exactly as in the Plane-era re-feed model today; nothing about them has changed in code yet.
- This grill should decide the **target roles** for Comments and Context *before* #049–#051 wire the resume/delta path, because the delta-only renderer (#049) is precisely where "what gets injected from each store" is encoded. Deciding it now avoids building the renderer against a memory model that is about to change.
