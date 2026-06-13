# Session — Session Resume continuity design (grill + ADR + issues)

- Date: 2026-06-13
- Actor: operator (James) + agent (Claude Code)
- Type: design / planning (no code shipped)
- Mode: `/grill-me` → `/to-issues` → ADR-0009 → wiki update

## Question that opened it

Operator asked for an alternative to how context is managed: each Podium Issue should behave "as if I'm in front of the CLI." Concern: a post-issue / get-response loop loses so much vs the CLI that real work in Podium would not be worth doing.

## Grounding established during the grill

- Current continuity is deliberately stateless: pi runs `--print --no-session` (`agent_runner.py:107-108,251-252`); operator-reply flips state to `todo` and the next Run re-feeds full `comments_md` + `context_md` into a fresh prompt. Documented as a chosen design in `wiki/concepts/operator-reply.md:60-62`.
- Both agents DO support sessions on the CLI we already drive: pi `--session-id <id>` ("creating it if missing"), Claude `--session-id <uuid>` (create) + `--resume <uuid>` (resume). Verified via `pi --help`, `claude --help`.
- Both namespace session files by cwd: Claude `~/.claude/projects/<encoded-cwd>/<id>.jsonl` (non-alphanumeric → `-`), pi `~/.pi/agent/sessions/<cwd-slug>/`.
- Docs verified (code.claude.com/agent-sdk/sessions, pi.dev/docs/sessions): a session persists the CONVERSATION, not the filesystem; "capture the session_id" is an Agent SDK feature (Symphony's Claude path is the tmux CLI, ADR-0001, not the SDK); Anthropic itself recommends re-feeding results over shipping transcript files for ephemeral/cross-host cases.

## Locked decisions (the grill resolved each branch one-by-one; operator agreed to all)

1. Universal (pi + Claude), but resume is best-effort with text re-feed as the guaranteed floor.
2. Goal = continuity quality; resume only counts if it lets us STOP re-feeding on follow-up runs.
3. Identity = derive `UUIDv5(issue.id)`; stay on the CLI/tmux path (no Agent-SDK migration); filesystem-probe for existence. Rejected: capture-via-SDK, capture-via-scrape.
4. Eligibility predicate (all must hold, else re-feed): same agent kind ∧ cwd present+unchanged ∧ session file present ∧ no git rug-pull (HEAD unchanged since session last ran). Scope: in_review/blocked reply loop only; Done-reopen and predicate failures fall back; worktree lifecycle (#021) untouched.
5. Resume prompt = mechanical wrapper + newest operator-reply delta only. Keep writing comments_md/context_md (UI + fallback) but stop injecting on resume. Skip #026 compaction on resume runs. WORKFLOW.md edit-mid-issue staleness accepted.
6. Persistence = two `run` columns (`agent_session_sha`, `resumed`); no pointer table; id stays derived. Rejected: `issue_session` table.
7. Runtime safety = ban `--continue` (silent-fresh hazard), explicit id only, catch-and-refeed in-tick, loud `resume_skipped`/`resume_failed` markers.

## Reality-check expansion (operator's "anything else for exploratory issues?")

Correction made in-session: dimensions 2 (interactive steering) and 3 (live visibility) are NOT as irreducible as first stated, given tmux persistence + session files on disk. Agreed scope: backbone + A + B + D.

- Backbone — Question Park: flip the current "never ask questions" wrapper (`claude_runner._wrap_prompt` + pi equivalent); agent may park to ask the operator, parked to `in_review` carrying the question; reply resumes the session with the answer.
- A — Live Session Tail: tail the session `.jsonl` (written live) and stream over the WS hub (#017); recovers in-flight visibility without changing the separate-process scheduler model (ADR-0006).
- B — Fast re-dispatch: reply writes a wake sentinel the scheduler watches; round-trip minutes → seconds.
- D — Checkpointed exploration: WORKFLOW/Skill prompt policy — bounded step then park, leaning on resume + Question Park.
- Deferred (recorded, no issues): C = live tmux send-keys mid-run steering (Claude-only, race-prone); E = `--fork` A/B exploration.

## Artifacts produced

- ADR-0009 (`docs/adr/0009-session-resume-continuity.md`; raw copy `wiki/raw/adr-0009-session-resume-continuity.md`).
- CONTEXT.md glossary terms: Continuity, Re-feed, Session Resume, Question Park, Session Tail.
- Kanban issues `.kanban/issues/047`–`055` (board archived 027–046 → `.kanban/archive/2026-06-13/`).

## Status / unresolved

- No code shipped. All of the above is design + backlog. Re-feed remains the live, current behavior.
- Stale glossary noted but NOT fixed (operator hold): CONTEXT.md "Agent" term still says "pi only / claude removed" while Agent Adapter term and #042–#046 say Claude is live.
- ADR-0009 marked `accepted` (operator greenlit creation; design locked) though unimplemented.
