# 04 — F1: Bubble rendering + Variant B visual + client merge + 2 run bubbles

**What to build:** opening an issue shows a chat-style thread — per-role bubbles (agent blue, operator green, patrol amber, system neutral grey, legacy grey), collapsed system rows, two system bubbles per run (start + terminal with verdict/summary), topbar state chip with sublabel vocabulary. `comments_md` is split on the §2.1 header regex; the run row is interleaved client-side by timestamp with the deterministic tie-break `(ts, kind_rank, id)`. Includes the agent-question "your turn" treatment (folded from spec F5 §8).

**Blocked by:** #30 (B1 — server must stamp new headers before the client can split on them).

**Status:** ready-for-agent

- [ ] Replace `<Markdown source={comments_md}/>` in the comments tab with a split-on-header bubble renderer using the spec §2.1 regex `^### (agent|operator|patrol|system) · (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$`
- [ ] Variant B visual: full-width blocks, role colors per spec §3; no left/right chat bubbles
- [ ] System rows collapsed by default (expandable); legacy un-headered buckets collapsed by default, neutral grey, no actor attribution, no timestamp
- [ ] Two run-system bubbles per run: start at `started_at` (`Run #N started · agent · model · skill`) + terminal at `ended_at` (verdict + summary: `parked-for-review` / `completed ✓` / `blocked` / `failed (exit N)` / `retry`)
- [ ] Stable-sort interleave with the `(ts, kind_rank, id)` rule; on collision, comment_bubble < run_start_bubble < run_terminal_bubble
- [ ] Topbar state chip with sublabel vocabulary: `todo`→queued, `running`→agent working, `in_review`→your turn, `blocked`→blocked, `done`→done, fresh `todo`→say something
- [ ] Pinned chat-native description card atop the thread (evolved from `IssueFlyout.tsx:1275–1279` muted-Markdown block)
- [ ] Update `web/frontend/tests/comments-collapse.spec.ts` to use new-format headers OR explicitly assert legacy-bucket rendering for old-format inputs

Verification: `uv run pytest web/frontend/tests/comments-collapse.spec.ts web/frontend/tests/flyout-tabs.spec.ts -q` (via Playwright)

Provenance: spec §1, §2, §3, §4, §13.1, §13.2, §13.3, §13.7; the spec's suggested F5 folded in (acceptance line for state-chip sublabel vocabulary covers the "your turn" treatment).

Wiki refs: [concepts/operator-reply.md], [concepts/podium-tracker.md].
