# 07 — F4: Creation rework (agent picker + pinned description + auto-open flyout)

**What to build:** the create form leads with a two-up `pi | claude` segmented control at the top; model picker filters to models valid for the chosen agent; description renders as a pinned chat-native header atop the thread; on create success, the modal closes and the flyout auto-opens with the composer focused after `finishIssue` resolves (the two-stage attachment flow must settle).

**Blocked by:** None — independent of B1/B2/B3 and of F1/F2/F3.

**Status:** ready-for-agent

- [ ] `NewIssueModal` two-up `pi | claude` segmented control as the topmost field; not one of six peer metadata fields
- [ ] Model picker filters to models valid for the chosen agent (existing agent-aware preselect preserved; no change)
- [ ] Description renders as a pinned chat-native card atop the flyout (evolved from the muted-Markdown block at `IssueFlyout.tsx:1275–1279` to a top-of-scroll issue card)
- [ ] On create success: close the modal, auto-open the chat flyout with the composer focused
- [ ] Auto-open sequenced after `finishIssue` resolves (the two-stage attachment flow must settle), not on bare create success
- [ ] No new column; no `comments_md` seed block written
- [ ] `preferred_agent` semantics unchanged (already synthesized into `agent:<preferred_agent>` labels at read time)
- [ ] Skill / effort / base stay secondary; description stays the body input

Verification: `uv run pytest web/frontend/tests/new-issue.spec.ts -q` (via Playwright)

Provenance: spec §10, §13.6.

Wiki refs: [concepts/podium-tracker.md].
