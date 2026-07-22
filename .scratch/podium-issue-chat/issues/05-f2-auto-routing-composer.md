# 05 — F2: Auto-routing composer + mode pill + conditional Abort

**What to build:** a single composer auto-routes by run state — five cases (reply / steer / comment × 3) plus Abort on steerable live runs. Mode pill on the send button always names mode + consequence. Today's separate `ReplyComposer` + `SteerComposer` collapse into one. Includes the "your turn" affordance for fresh `todo` and `in_review` (folded from spec F5 §8 — `state=in_review` after an agent question park is the actionable state paired with the composer pill).

**Blocked by:** #33 (F1 — depends on the new topbar state chip and the chat-native description card).

**Status:** ready-for-agent

- [ ] Five-case routing covers every issue state per §7
- [ ] Mode pill visible at all times; pill text: `Reply · re-dispatches` / `Steer · live` / `Comment · note` / `Comment · agent sees it next park` / `Comment · seed`
- [ ] Abort button only visible on steerable live runs (reuses `canSteer` derivation from `IssueFlyout.tsx:762`); Abort rides the same `steer_issue` RPC gate as steer
- [ ] Composer auto-focuses on fresh `todo` after create (§7 fresh-todo case)
- [ ] Reply-disabled-hint copy updated for the new modes
- [ ] The "your turn" affordance shows when `state=in_review` (fold F5)
- [ ] Single composer replaces `ReplyComposer` + `SteerComposer`; one query + one send handler

Verification: `uv run pytest web/frontend/tests/reply.spec.ts web/frontend/tests/steer-flyout.spec.ts -q` (via Playwright)

Provenance: spec §7, §13.4; spec's suggested F5 folded in (state=in_review affordance).

Wiki refs: [concepts/operator-reply.md].
