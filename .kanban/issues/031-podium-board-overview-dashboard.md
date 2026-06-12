---
id: 031
title: Podium — board-level overview dashboard at /
status: review
blocked_by: []
parent: null
priority: 0
created: 2026-06-12
updated: 2026-06-12
actor: ralph
---

## What to build

Replace the landing placeholder (`web/frontend/app/page.tsx` — "Pick a
binding from the sidebar") with an at-a-glance cross-binding dashboard. All
data is computable client-side from the existing issue-list payload
(`web/api/main.py:369` already returns `state`, `latest_run_state`,
`latest_verdict`, `last_event_at` per issue) — **no new backend endpoint**.
There are two bindings, so client-side aggregation is trivial.

Decision: UX/observability tuning plan; failure-trend chart deliberately
deferred (would need a new run-history aggregate endpoint). See
`wiki/analyses/adr-0006-engine-state-polling.md`.

**1. Data.**

The `/` page fetches `fetchBindings()` then each binding's issues (reuse the
existing `["issues", binding]` query via `fetchBindingIssues`). Skip
bindings where `binding.archived` is true. Aggregate per binding and
globally.

**2. Live state counts.**

Per-binding + global tallies keyed off `issue.state` so the dashboard
agrees with the board columns (`lib/issues.ts` `STATES` / `KanbanBoard.tsx`):
queue depth (`state==='todo'`), running (`state==='running'` — **not**
`latest_run_state`, which would disagree with the board), in_review
(`state==='in_review'`), blocked (`state==='blocked'`), done
(`state==='done'`). Render as per-binding summary cards plus a global
roll-up.

**3. Attention list.**

A flat cross-binding "needs you" list: issues where `state==='blocked'`
**or** `latest_verdict==='blocked'` **or** `latest_run_state==='failed'`.
Each row links through to the issue flyout via `/<binding>?issue=<id>`.

**4. Deep-link to flyout.**

Not currently supported: the flyout's selected-issue id is local `useState`
inside `KanbanBoard` (`KanbanBoard.tsx:15`, set by `IssueCard` onClick), and
`BindingPage` (`app/[binding]/page.tsx`) never reads search params. To make
`/<binding>?issue=<id>` work, `BindingPage` reads
`useSearchParams().get('issue')` and passes it to `KanbanBoard` as an
`initialIssueId` prop that seeds `selected`; closing the flyout clears the
`?issue=` param (e.g. `router.replace('/<binding>')`). Keep card-click
behavior unchanged.

**5. Per-binding last activity.**

Show each binding's most recent `last_event_at` (max across its issues) so a
binding gone quiet is visible.

Gated polling (#029) keeps the dashboard fresh; if #029 has not landed, the
dashboard is still correct on load / refocus.

## Acceptance criteria

- [ ] `/` renders per-binding summary cards (archived bindings skipped) with queue/running/in_review/blocked/done counts keyed off `issue.state`, plus a global roll-up, computed from the issue-list payload (no new endpoint).
- [ ] Attention list shows blocked + latest-run-failed issues across all bindings; empty state when none.
- [ ] Clicking an attention row navigates to `/<binding>?issue=<id>` and opens that issue's flyout.
- [ ] Each binding card shows a last-activity timestamp from `last_event_at`.
- [ ] Playwright: seed mixed states across bindings → assert counts, attention list membership, and click-through-opens-flyout.
- [ ] `pnpm exec tsc --noEmit` passes.

## Verification

```
cd /home/james/symphony && uv run pytest && \
cd web/frontend && pnpm exec tsc --noEmit && pnpm test:e2e
```

## Blocked by

- none (pairs with #029 for liveness)
