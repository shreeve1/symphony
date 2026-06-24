---
id: 110
title: UI — read-only "waiting on #N" / "locked: <label>" chip on gated todo cards
status: in-progress
blocked_by: [105, 107]
locks: [web-frontend]
priority: 2
created: 2026-06-23
---

## What to build

Per ADR-0021 (P2), give the operator a read-only cue for *why* a `todo` issue isn't
running — dependency or lock. No control surface (operator dropped
start/stop/control) — display only.

- `GET` issue payload exposes `blocked_by` (ids), `locks` (labels), and a derived
  `dependencies_satisfied` boolean (all blockers done/archived).
- On an issue card / flyout, when a `todo` issue has unsatisfied blockers, show a
  small "Waiting on #N, #M" chip. When it holds locks that intersect a running
  issue's locks, show a "Locked: <label>" chip. Satisfied/no-deps/no-lock issues
  show nothing.
- Do not invent a new column or state; the issue stays in the `todo` column.

## Acceptance criteria

- [ ] A dependency-gated `todo` issue shows a "Waiting on #N" chip listing unmet
      blockers.
- [ ] A lock-gated `todo` issue (locks intersect a running issue) shows a
      "Locked: <label>" chip.
- [ ] When blockers close / the lock holder finishes, the chip clears (live via
      existing WS refresh).
- [ ] No edit/control affordance is added.

## Verification

`pnpm -C web/frontend exec playwright test dependency-chip.spec.ts`
(add the spec as part of this slice)
