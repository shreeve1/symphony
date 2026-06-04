---
id: 002
title: Tracker Adapter seam
status: pending
blocked_by: [1]
parent: null
priority: 0
created: 2026-06-04
---

## What to build

Introduce a Tracker Adapter interface that isolates every Plane-specific API
call behind one seam, so the engine talks to "a tracker" rather than to Plane
directly. `PlaneTrackerAdapter` is the single implementation; it resolves an
issue's Roles for its binding (using the contract from #001), lists candidate
issues, posts comments, and transitions states. The engine selects and drives
the adapter without knowing it is Plane.

This is the concrete shape of the Tracker Adapter seam in
`docs/adr/0002-generalize-symphony-over-adopting-a-platform.md`. Pure refactor —
no behavior change.

## Acceptance criteria

- [ ] No engine module issues Plane HTTP calls (httpx / plane_cli) outside the adapter.
- [ ] The adapter exposes role-resolution + the issue lifecycle ops the engine needs (list candidates, comment, set state).
- [ ] Engine code references the adapter interface, not a concrete Plane client type.
- [ ] All existing scheduler/poller behavior is preserved (suite green).

## Verification

`uv run pytest`

## Blocked by

- Blocked by #1
