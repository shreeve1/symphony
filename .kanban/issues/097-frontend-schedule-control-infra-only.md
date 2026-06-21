---
id: 97
title: Frontend Schedule control (infra-only) — new-issue modal + flyout
status: pending
blocked_by: [96]
parent: null
priority: 0
created: 2026-06-21
---

## What to build

The Podium UI Schedule control, shown only for infra bindings, on top of the
issue-96 endpoints.

1. Add a Schedule control to `web/frontend/components/NewIssueModal.tsx` and
   `web/frontend/components/IssueFlyout.tsx`, rendered only when
   `binding_type === "infra"` (issue rows already carry `binding_type`;
   `/api/bindings` now exposes it for the modal — pass it in, do NOT infer from the
   binding name; remove the stale `binding === "trading" ? "coding" : "infra"`
   heuristic).
2. Options: **Next maintenance window** (default — sends `not_before: "next_window"`,
   server resolves the time), **Custom date-time** (sends ISO8601 with offset),
   **None**. Include a **reason** input (default `"operator scheduled via Podium"`).
   Surface the scheduled state + `not_before` on the flyout.
3. New-issue scheduling uses the issue-96 atomic create-and-schedule path (not a
   future `scheduled_for` via `IssueCreate`). Existing-issue scheduling calls
   `POST /api/issues/{id}/schedule`; unscheduling calls `DELETE`.
4. Replace the existing raw `scheduled_for` `ChipText` in `IssueFlyout.tsx` with the
   new control; stop using `IssuePatch.scheduled_for` as a manual scheduling path.
5. Wire optimistic update + cache invalidation through the existing TanStack Query
   cache (mirror the reply/steer mutations).
6. **Board-card scheduled indicator (gap fix):** a held-scheduled issue sits in the
   Todo column looking identical to an actionable Todo — `IssueCard.tsx` /
   `KanbanBoard.tsx` currently show nothing. Add a "Scheduled" chip to
   `web/frontend/components/IssueCard.tsx` driven by the derived `scheduled` label /
   `scheduled_for` (with `not_before` on hover/title) so deferred-to-window Todos are
   distinguishable at a glance.
7. Add `web/frontend/tests/schedule.spec.ts` covering the control AND the card chip.

## Acceptance criteria

- [ ] The Schedule control renders for an infra binding's new-issue modal and flyout, and does NOT render for a coding binding.
- [ ] Selecting "Next maintenance window" schedules via the endpoint with `not_before:"next_window"`; "Custom" sends an ISO8601-with-offset value; a reason is always sent (default applied).
- [ ] New-issue scheduling uses the atomic create-and-schedule path (issue held immediately, no raw future `scheduled_for`).
- [ ] The raw `scheduled_for` `ChipText` is removed from `IssueFlyout.tsx`; manual scheduling no longer goes through `IssuePatch.scheduled_for`.
- [ ] `IssueCard.tsx` renders a "Scheduled" chip for a held-scheduled Todo and nothing for an unscheduled Todo.
- [ ] `web/frontend/tests/schedule.spec.ts` exists and passes (control + card chip); the frontend builds.

## Verification

`cd web/frontend && pnpm test:e2e schedule.spec.ts && pnpm build`

## Blocked by

- Blocked by #96 (the `/schedule` endpoints, `binding_type` on `/api/bindings`, and the atomic create-and-schedule path).
