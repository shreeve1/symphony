# Session Capture: Issue flyout comment ordering + single-blob render

- Date: 2026-06-16
- Purpose: Operator found the flyout comment thread "difficult to follow" (newest-first ordering) and asked to render the summary as plain markdown. Reworked `CommentsThread` rendering and ordering.
- Scope: Frontend display-only change to `web/frontend/components/IssueFlyout.tsx`; plus a verified pre-existing e2e-suite drift discovered while running Playwright.

## Durable Facts

- Before this change, `CommentsThread` split `comments_md` on any markdown heading via `splitCommentEntries` (regex `/\n(?=#{1,6} )/g`), wrapped each fragment in a `comment-entry` card, and rendered newest-first via `.reverse()`. — Evidence: pre-change `IssueFlyout.tsx:595-638` (git HEAD before working-tree edit)
- The `#{1,6}` split was a latent display bug: a `### Symphony AI Summary` containing sub-headings (`#### …`, `## …`) was shredded into multiple cards, and `.reverse()` then scrambled those fragments out of order. — Evidence: `IssueFlyout.tsx` split regex + the comment-type grammar (`### Operator Reply`, `### Symphony AI Summary`) at `tracker_podium.py:500`, `web/api/main.py:1179`
- New behavior: `comments_md` renders as a single `<Markdown>` block inside one bordered card, in stored chronological order (oldest-first), with auto-scroll to the bottom on open via a `ref` + `useEffect` keyed on `issueId` (not `source`, to avoid a background poll yanking the operator mid-read). `splitCommentEntries` and the `comment-entry` testid were removed; the `view-comments_md` container testid is retained. — Evidence: `web/frontend/components/IssueFlyout.tsx` (`CommentsThread`, ~line 595+); `git diff --stat` = 34 insertions / 35 deletions, one file
- `comment-entry` testid is referenced only inside `IssueFlyout.tsx`; no test depends on it (safe to drop). `view-comments_md` is asserted by `flyout-tabs.spec.ts:23,33` and `steer-flyout.spec.ts:62,65` (all `toContainText`) so single-blob render keeps them green. — Evidence: `grep comment-entry web/frontend/tests` = no match; grep `view-comments_md` = those four lines
- e2e drift (pre-existing, NOT from this change): `flyout-tabs.spec.ts`, `board.spec.ts`, `run-detail.spec.ts` hard-depend on a `trading` binding — they `page.goto("/trading")` and filter for the seed card "Seed running issue for trading". `tests/global-setup.mjs` builds the fixture `bindings.yml` by mirroring the live `bindings.yml` entries (rewriting only `repo_path`). Since the `trading` binding was offboarded/purged from live `bindings.yml`, the fixture has no `trading` binding, the `/trading` board renders no card, and those specs time out at the `issue-card` click. Confirmed by stashing the working-tree edit and re-running on clean HEAD: identical failure. — Evidence: `flyout-tabs.spec.ts:7,12`; `tests/global-setup.mjs:9-10,30-47`; `tests/fixtures.ts:118-142` (`seedIssue`); clean-HEAD re-run

## Decisions

- Render comments as one chronological markdown blob, oldest-first (option A — "remove the entry split"), not per-entry cards. — Evidence: this session; operator picked A over a fixed-regex card option (B)
- Newest-first ordering is reversed back to oldest-first because the operator found newest-first hard to follow; visibility of the latest entry is preserved by auto-scroll-to-bottom instead. — Evidence: this session
- Auto-scroll effect keyed on `issueId` (open-only), not `source` (every update), to avoid yank-on-poll. — Evidence: this session

## Evidence

- `web/frontend/components/IssueFlyout.tsx` — the changed `CommentsThread` (single-blob render, oldest-first, issueId-keyed auto-scroll) and updated call site `<CommentsThread issueId={issue.id} source={issue.comments_md} />`
- `web/frontend/tests/steer-flyout.spec.ts` — passing; exercises `view-comments_md` against the new render
- `web/frontend/tests/flyout-tabs.spec.ts`, `tests/global-setup.mjs`, `tests/fixtures.ts` — the trading-binding e2e dependency
- Verification: `npx tsc --noEmit` exit 0; `npx playwright test flyout-tabs steer-flyout` = 3 passed / 1 failed (the trading-drift failure)

## Exclusions

- No secrets, env values, or `symphony-host.env` content. No full transcript.

## Open Questions And Follow-Ups

- The flyout change is uncommitted at capture and lives only in the working tree; `podium-web.service` serves a prebuilt bundle, so showing it in the live UI needs `web/frontend/deploy.sh` (rebuild + atomic swap), not a plain restart (per C-0218 deploy topology).
- Follow-up (not done at first capture): the `trading`-bound e2e specs are broken by the trading offboarding. Either reseed those specs against a still-live binding or restore a fixture-only `trading` binding in `global-setup.mjs`.

## Addendum (same session) — e2e drift resolved

- Full-suite run revealed the breakage was **16 specs, not 3**: `seedIssue("trading", …)` hit `FOREIGN KEY constraint failed` (`issue.binding_name REFERENCES binding(name)`, `web/api/schema.py:28`) for the mutating specs (`board-dnd`/`archive`/`dashboard`/`reply`); the read-only specs (`board`/`run-detail`/`flyout-tabs`) timed out on the missing seed card.
- Operator chose **decouple over migrate**: migrating to `homelab` would collide because the mutating specs use `trading` as a board isolated from the homelab specs under `fullyParallel` (dashboard counts, dnd/archive state).
- Fix (commit `b3e0f58`): `global-setup.mjs` synthesizes a fixture-only `trading` binding — deep-copy a local binding, force `type=coding`, drop any `remote:` block. `type=coding` is required because the flyout's 7-chip layout is the coding layout; infra bindings add 3 chips (`IssueFlyout.tsx:314`, `web/api/main.py:859`). No spec edits.
- Verified: full suite **47 passed**, lone miss is an unrelated `new-issue` combobox keyboard-timing flake (green in isolation). — Evidence: `web/frontend/tests/global-setup.mjs`, commit `b3e0f58`
