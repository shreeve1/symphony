---
id: 039
title: Podium — remove dashboard attention list (superseded by Inbox)
status: pending
blocked_by: [037]
parent: null
priority: 0
created: 2026-06-12
---

## What to build

Remove the dashboard "Needs attention" section. The sidebar Inbox (#037) is the sole "needs operator" surface: its membership (`in_review` + `blocked`) is a strict superset of what the attention list caught (failed runs already land in `blocked` via the scheduler's `_block_issue`), and it adds dismissal and chronological ordering. Keeping both surfaces would drift apart and confuse.

In `web/frontend/app/page.tsx`:

- Delete the attention section markup (`data-testid="dashboard-attention"`, the "Needs attention" header, and `data-testid="attention-row"` rows).
- Delete the `attentionItems` computation (around lines 177-186) and any now-unused imports/helpers it leaves behind. Touch nothing else on the dashboard — the rollup and other sections stay as-is.

In `web/frontend/tests/dashboard.spec.ts`: remove or rewrite assertions that reference `dashboard-attention` / `attention-row` so the suite reflects the removal (an explicit assertion that the section is absent is acceptable but not required).

This slice is intentionally tiny: it is the second half of the "replace attention list with Inbox" decision and lands only after the replacement exists.

## Acceptance criteria

- [ ] `app/page.tsx` contains no `dashboard-attention` or `attention-row` testids and no `attentionItems` computation; no orphaned imports or variables remain from the removal.
- [ ] `grep -rn "attention" web/frontend/app web/frontend/components` returns no matches.
- [ ] `tests/dashboard.spec.ts` passes with the section gone; no spec in the suite still expects the attention section.
- [ ] Full e2e suite passes.

## Verification

```
cd /home/james/symphony/web/frontend && pnpm test:e2e
```

## Blocked by

- Blocked by #037
