# Handoff — grill-me: standardize Symphony/Podium dispatch on tmux (move pi off one-shot)

**For:** a future `/grill-me` session.
**Date created:** 2026-06-13.
**Operator goal (verbatim intent):** move toward more *exploratory and control* in issues. Switch pi from its one-shot subprocess to a tmux interactive session like Claude, to **standardize how Symphony and Podium dispatch both agents**, and to be able to **tail pi's logs and steer pi mid-run** the way Claude can. Operator notes the original dispatch model wasn't planned for this and wants to correct course.

> Grill discipline: treat "switch pi to tmux" as the **leading hypothesis, not a settled decision**. The real goal is tail + steer + one standard dispatch model. Test the hypothesis against alternatives before committing. Resolve the design tree one branch at a time, recommend an answer per question, update `CONTEXT.md`/ADRs inline.

---

## Why this is non-trivial (the honest tension)

Symphony deliberately went **thin-engine v2**: pi dispatches one-shot, worktrees were removed, and the Claude tmux path was *paused* specifically to shed tmux/session complexity (`wiki/concepts/thin-engine-v2.md`). Claude was then **reintroduced via tmux** (2026-06-13, #042–#046) and immediately surfaced a whole fragility class — paste/Enter races, done-before-result races, heredoc-write breakage, orphan sockets, `PrivateTmp` socket isolation (`C-0174`). Moving pi onto tmux means **putting that entire fragility class onto the currently-robust, proven, deterministic pi path** (pi one-shot is covered by 700+ passing tests and is live). That is the central trade-off the grill must weigh: standardization + steer/tail vs. re-thickening the engine the project intentionally thinned.

This is squarely **ADR territory** — it generalizes ADR-0001 (Claude-via-tmux) to all agents and partially reverses the thin-engine "pi one-shot" posture.

---

## Grounded facts (verified this session)

**Current pi dispatch (one-shot, non-interactive):**
- `pi --print --no-session --provider <p> --model <m>` from the bound repo cwd (`agent_runner.py:107-108,251-252`). `--print` = non-interactive batch; `--no-session` = ephemeral.
- Completion = process exit; `process.communicate(timeout=…)` captures all stdout/stderr at once (`agent_runner.py:272`) → **no incremental output, no live tail** (ADR-0006).
- pi *does* support sessions and an interactive TUI: `pi --help` shows `--session-id <id>` (create-or-resume), `--resume/-r`, `--continue/-c`, `--session-dir`, `PI_CODING_AGENT_SESSION_DIR`; sessions are JSONL under `~/.pi/agent/sessions/<cwd-slug>/`. `--print` is the opt-in that *disables* interactivity. So an interactive pi-in-tmux is plausible — the open question is the completion-signal protocol.

**Current Claude dispatch (tmux interactive — the template to standardize on):**
- `claude_runner.py`: `tmux new-session -d ... claude --permission-mode bypassPermissions --model <m>` on a per-run socket `/tmp/symphony-claude-<issue>-<nonce>.sock`.
- Drives the TUI by send-keys: ready-poll on pane text, `load-buffer`+`paste-buffer`, settle + retry Enter (`_paste_and_submit`, `PASTE_SETTLE_SECONDS`, `SUBMIT_RETRY_ATTEMPTS`).
- **Completion protocol** (`_wrap_prompt`): agent writes full output to a `result.txt` path via its Write tool (not heredoc), then creates a `done` file *only after* verifying result non-empty; runner polls for `done`, reads result with a grace window (`_read_result_with_grace`, `RESULT_GRACE_SECONDS`), captures pane on failure.
- Startup probe (`verify_claude_support`, `C-0156`) + orphan socket reaper (`reap_orphan_claude_sockets`, `C-0158`). `symphony-host.service` has `PrivateTmp=yes` → per-run sockets live in the service's private `/tmp` (observe via `nsenter`, `C-0174`).
- Routing: `RoutingAgentAdapter` picks pi vs claude per issue (`C-0153`).

**Architecture constraints:**
- Scheduler is a **separate process** from the web/API; the WS hub is in-process and never sees engine state — engine state is surfaced by gated polling, and there is no live log tail today (ADR-0006). Any "tail pi logs in Podium" must respect this (the session jsonl file is a live stream even though the per-run log is written once at exit — same lever as Session Tail issue #053).

**In-flight design that this intersects (ADR-0009 + issues 047–055, design-stage, unimplemented):**
- Session Resume continuity: derive `UUIDv5(issue.id)`, best-effort resume over a re-feed floor, scoped to the in_review/blocked reply loop. For pi it currently assumes `--session-id` *with `--print`* — **if pi goes interactive-tmux, reconcile how pi resumes (TUI `--resume`/`-c`) and whether the `--print` Session Resume path is dropped or kept.**
- Issue #053 = Live Session Tail (tail the agent session jsonl over the WS hub). This handoff's "tail pi logs" goal is essentially #053 generalized to pi — they should be designed together.
- **Deferred item "C" = live tmux send-keys mid-run steering** (was Claude-only, race-prone). The operator's "steer pi like Claude" goal is exactly this, made universal. If both agents are tmux, C becomes one mechanism for both — **this handoff is the reason to un-defer C.**

---

## Design tree the grill must resolve (suggested order)

1. **Feasibility gate (verify first, don't assume):** can pi run interactively (no `--print`) under tmux send-keys with a *deterministic* completion signal? Confirm the `result.txt`+`done` file protocol works for pi's TUI exactly as for Claude (pi has a Write/file tool? does it reliably create the done file?). If pi can't be driven headlessly to a clean completion signal, the whole hypothesis fails — fall back to alternatives (below).
2. **Standardize fully, or dual-mode?** All pi dispatch via tmux, or keep `--print` one-shot for non-interactive/cheap bindings and use tmux only when steer/tail is wanted per-issue? (Trade-off: one code path + universal steer/tail vs. paying tmux overhead + the C-0174 fragility class on every pi run.)
3. **Shared runner module?** Extract `claude_runner`'s tmux mechanics (socket naming, ready-poll, paste/submit, result/done protocol, grace read, pane capture, reaper, probe) into one shared `tmux_runner` that both pi and claude adapters use. Define the per-agent deltas (launch argv, ready pattern, model/provider handling).
4. **Steering (un-defer C):** send-keys interjection into the live pane — how to make it safe against the done-file completion gate and mid-tool-call injection, for both agents. What's the Podium UX (a "nudge" box in the flyout)? What are the race/ordering guarantees?
5. **Log tail (= #053 generalized):** standardize the tail source on the agent session jsonl for both pi and claude; stream over the WS hub; respect the separate-process model (ADR-0006). Reconcile with #053's scope.
6. **Session Resume reconciliation (ADR-0009):** if pi becomes interactive-tmux with native sessions, how does pi resume (TUI `--resume <id>` / `-c` / `--session-id`)? Does the `--print --session-id` resume path in ADR-0009 get dropped? Does `--no-session` stop being the floor for pi?
7. **Operational cost:** per-run tmux sockets for *every* pi dispatch — orphan reaping at pi scale, `PrivateTmp` observability, startup probe for pi, concurrency cap interaction. What's the overhead vs. one-shot subprocess?
8. **Blast radius / migration:** pi one-shot is the proven path (live, 700+ tests). What's the rollout — feature-flag per binding, soak, keep one-shot as rollback? How do the existing pi tests (`test_agent_runner`, dispatch/compaction) change?

## Alternatives to test the hypothesis against (don't skip)
- pi's own streaming/session APIs or an SDK (does pi expose incremental output without a TUI? a JSON event stream? an embeddable mode?) — could deliver tail+steer *without* tmux fragility.
- Tail-only without steer (cheaper): get #053 working for pi via the session jsonl while keeping `--print --session-id` dispatch — gives visibility without the interactive-completion problem. Decide whether steer is worth the tmux cost.
- Keep two dispatch shapes but unify the *observability* (tail) and *continuity* (resume) layers, accepting that "steer" stays Claude-only. (Is full standardization actually required, or is the real want tail+steer?)

---

## Pointers
- Code: `agent_runner.py` (pi one-shot + `verify_pi_support`), `claude_runner.py` (tmux template), `scheduler.py` (`RoutingAgentAdapter`, dispatch gate), `prompt_renderer.py` (`OUTPUT_CONTRACT`), `main.py` (probe + reaper wiring).
- ADRs: `docs/adr/0001-claude-via-tmux-send-keys.md`, `0006-engine-state-surfaced-by-polling-not-websocket.md`, `0009-session-resume-continuity.md`. (New ADR likely needed: "standardize dispatch on tmux / generalize ADR-0001".)
- Wiki: `concepts/thin-engine-v2.md`, `concepts/agent-runner-and-worktree.md`, `concepts/session-resume-continuity.md`, `analyses/podium-042-claude-tmux-adapter.md`, `analyses/podium-043-claude-dispatch-routing.md`, `analyses/podium-044-claude-startup-probe-reaper.md`. Claims `C-0153`, `C-0156`, `C-0158`, `C-0174`.
- Backlog this intersects: `.kanban/issues/047`–`055` (Session Resume + Question Park + Session Tail #053 + fast re-dispatch + checkpointed exploration). The deferred "C" (live send-keys steering) lives only in `wiki/concepts/session-resume-continuity.md` and `C-0176`.
- CONTEXT.md glossary already has: Agent, Agent Adapter, Continuity/Re-feed/Session Resume, Question Park, Session Tail. A successful grill likely adds a term for the unified tmux dispatch model and/or "steering/interjection".

## State at handoff
- Session Resume (ADR-0009) + issues 047–055 are **design-stage, unimplemented**; live behavior is still pure re-feed + pi one-shot. None of it is committed (live-infra repo; operator reviews/commits).
- This pivot likely **re-sequences** the backlog: if pi→tmux lands first, Session Tail (#053) and steering (C) become universal and the pi-side of #050 changes. The grill should decide ordering: does pi→tmux standardization come *before* or *after* the Session Resume core?
