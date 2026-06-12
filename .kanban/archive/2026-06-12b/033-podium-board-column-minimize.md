---
id: 033
title: Podium — per-column board minimize with localStorage persistence
status: done
blocked_by: []
updated: 2026-06-12
actor: ralph
parent: null
priority: 0
created: 2026-06-12
---

## What to build

General minimize/expand control on every kanban board column, per the accepted
design in `wiki/analyses/podium-issue-archive-design.md`. Each column header in
`web/frontend/components/KanbanBoard.tsx` gets a minimize (−) button; a
collapsed column renders as a narrow vertical strip (state dot, issue count,
and an expand (+) button) instead of the full `w-72` card list. Collapse state
persists in localStorage keyed per binding (`podium.collapsed.<binding>`,
storing an array of collapsed state keys) so the board remembers the
operator's layout across reloads. Default when no stored value exists: all
columns expanded.

This slice also carries the e2e isolation fix from C-0120: the Playwright
`webServer` command in `web/frontend/playwright.config.ts` currently runs bare
`pnpm exec next dev`, which writes a dev build into the production
`web/frontend/.next` that `podium-web.service` serves. Prefix the web-server
command with `NEXT_DIST_DIR=.next.e2e` (the override already exists in
`next.config.mjs:11`) and add `.next.e2e` to the frontend `.gitignore`, so
this slice and every later one can run e2e safely against the live checkout.

Follow the existing sidebar-collapse pattern (`podium:sidebar-open` in
`AppShell.tsx`) for localStorage read/write hygiene (SSR-safe access, JSON
parse with fallback).

## Acceptance criteria

- [x] Every board column header shows a minimize control; clicking it collapses the column to a narrow strip showing the state dot, issue count, and an expand control; clicking expand restores the full column.
- [x] Collapsed columns still reflect live issue counts.
- [x] Collapse state round-trips through localStorage key `podium.collapsed.<binding>` and survives a page reload; bindings have independent collapse sets.
- [x] Corrupt or missing localStorage value falls back to all-expanded without throwing.
- [x] `web/frontend/playwright.config.ts` web-server command sets `NEXT_DIST_DIR=.next.e2e`; `.next.e2e` is gitignored; running the e2e suite leaves the production `web/frontend/.next` untouched (no `BUILD_ID` overwrite).
- [x] New `web/frontend/tests/board-minimize.spec.ts` covers: collapse, expand, reload persistence, and per-binding independence.

## Verification

```
cd /home/james/symphony/web/frontend && pnpm test:e2e
```

## Implementation Notes

Implemented per-column minimize/expand controls in `KanbanBoard`, persisted collapsed state per binding with `podium.collapsed.<binding>`, added corrupt-storage fallback coverage, and isolated Playwright Next dev output with `NEXT_DIST_DIR=.next.e2e`. Verified production `.next/BUILD_ID` remains present after e2e.

Review returned `PASS_WITH_NOTES`: reviewer observed one unrelated e2e network-abort flake in `editing.spec.ts`; the full suite passed before review and all new board-minimize tests passed in both runs.

## Blocked by

None — can start immediately.
