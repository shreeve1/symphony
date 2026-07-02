---
id: 126
title: Save issue flyout reply drafts per issue
status: done
priority: 2
created: 2026-06-24
updated: 2026-06-26
actor: symphony
---

## What to build

When an operator types in the issue flyout reply box, switches to another issue,
and then returns, the unsent text should still be there.

Root cause: `ReplyComposer` owns its draft with component-local `useState("")` in
`web/frontend/components/IssueFlyout.tsx`. Switching `issueId` changes the React
Query key, the detail pane can briefly render the loading branch, and the composer
unmounts. Returning to the original issue remounts with an empty draft.

Implement the smallest fix:

- Persist only the reply/comment composer draft.
- Key drafts by issue id. A single lifted draft would leak issue A text into issue B.
- Back the draft with `sessionStorage` so it survives issue switches and browser
  refreshes in the same tab/session.
- Clear that issue's saved draft after a successful Send.
- Keep staged dispatch controls unchanged; they intentionally reset on issue switch.
- Leave `SteerComposer` out of this slice. It has the same local-draft behavior, but
  the reported problem is the reply/comment composer.

## Acceptance criteria

- [x] Typing in issue A's reply composer, opening issue B, then reopening issue A
      restores issue A's unsent draft.
- [x] Issue B does not show issue A's draft.
- [x] Refreshing the browser while issue A is open restores issue A's draft.
- [x] Sending a reply/comment clears the saved draft for that issue.
- [x] Staged schedule/approval controls still reset on issue switch.
- [x] No backend/API/schema changes.

## Verification

`cd web/frontend && pnpm test:e2e -- reply.spec.ts`

## Implementation Notes

- Added `sessionStorage` persistence for `ReplyComposer` drafts under
  `podium.reply-draft.<issue-id>`.
- Keyed `ReplyComposer` by issue id so cached issue switches cannot leak one issue's
  draft into another issue.
- Added Playwright coverage for per-issue restore, browser reload restore,
  clear-on-send, and unchanged staged schedule reset behavior.

## Notes

- Use `sessionStorage`, not `localStorage`; no cross-tab/permanent draft retention or
  cleanup policy needed.
- No ADR or `CONTEXT.md` update: this is a reversible frontend UX fix, not a domain
  or architecture decision.
