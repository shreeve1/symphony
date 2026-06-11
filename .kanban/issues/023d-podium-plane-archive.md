---
id: 023d
title: Plane archive — trading + homelab projects + Authelia route
status: blocked
blocked_by: [023c]
parent: null
priority: 2
created: 2026-06-10
updated: 2026-06-11
actor: ralph
---

## What to build

After both bindings are stable on Podium, archive the underlying Plane
projects and finalize the Authelia route to Podium.

**Operator soak gate** (wall-clock, NOT Ralph-verifiable): both bindings
should run on Podium for at least one operator-confirmed week before this
issue is picked up. The kanban completion note records the soak start
date; James confirms readiness in writing in this issue's completion
notes before any Plane archive is invoked.

**1. Plane archive.**

Invoke `symphony-plane-recover archive` against the `trading` project,
then `homelab`. Each is an explicit typed-confirmation step per the skill.
After archive: the project remains in Plane in an archived state for the
read-only audit window, but Symphony no longer touches it.

**2. Authelia route.**

Add Podium to the Authelia reverse-proxy config so the localhost-bound
Podium UI (`127.0.0.1:8091`) is reachable via the existing Authelia
gate on port `9091`. Reverse-proxy rule mirrors the pattern for the
other internal services on the host.

This step is operator-side infrastructure outside this repo; Ralph
authors the Authelia config snippet in `web/README.md` under a
"Reverse proxy" section but does not edit Authelia itself.

**3. Final CONTEXT.md edit.**

Remove the rollback-only references to Plane (commented-out blocks in
`bindings.yml`). After this issue lands, Plane is dormant; the Plane
adapter remains in source for the v2 hedge but is uncalled.

## Acceptance criteria

- [ ] Issue completion notes record: soak start date for trading, soak start date for homelab, James's explicit "soak passed" confirmation timestamp for each.
- [ ] `symphony-plane-recover archive` invoked successfully for both projects (capture the typed-confirmation transcript in completion notes).
- [ ] Plane projects show as archived in the Plane UI (operator-verified).
- [ ] `web/README.md` has a "Reverse proxy" section with the Authelia config snippet.
- [ ] Operator-confirmed: Podium reachable through Authelia at the documented URL.
- [ ] Commented-out Plane blocks removed from `bindings.yml`.
- [ ] Final `CONTEXT.md` Plane references either removed or marked `(retired YYYY-MM-DD)`.

## Verification

Operator-driven (irreversible step). Ralph drafts the Authelia config
snippet and the README updates; the Plane archive call and Authelia edit
require operator confirmation at the moment of action.

```
cd /home/james/symphony && uv run pytest
```

## Blocked by

- #023c (both bindings must be on Podium and stable before archive)

## Notes

- Irreversible (Plane archive). Operator-only execution.
- After this issue lands, the only Plane code path remaining is the
  dormant `plane_adapter.py` kept as the ADR-0002 hedge.

## Blocker

2026-06-11: Ralph did not invoke the Plane archive or edit Authelia because the issue's own soak gate is not satisfied. #023c landed on 2026-06-11, so the required one-week Podium soak has not elapsed, and this issue contains no James-written completion note confirming the trading and homelab soak passed with timestamps.
