---
title: "Podium #023d — trading Plane archive + reverse-proxy docs"
type: analysis
status: promoted
created: 2026-06-11
updated: 2026-06-12
sources:
  - wiki/raw/sessions/2026-06-11-podium-023d-trading-plane-archive.md
  - .kanban/issues/023d-podium-plane-archive.md
  - bindings.yml
  - CONTEXT.md
  - web/README.md
  - /etc/systemd/system/podium-web.service
confidence: high
tags: [podium, plane, archive, trading, bindings, reverse-proxy, authelia, 023d, soak-gate, deferred]
---

# Podium #023d — trading Plane archive + reverse-proxy docs

Issue #023d was the final Plane-retirement step after the trading and homelab
Podium cutovers (#020, #023c). It was **descoped to trading-only** during this
session; the homelab Plane archive was deferred to a follow-up issue.

## What happened

1. **Soak gate waived.** The issue's own gate required the trading binding to
   run on Podium for one operator-confirmed week before archive, plus a
   James-written "soak passed" timestamp. #023c (homelab cutover) had landed the
   same day, so the week had not elapsed. James overrode the gate: trading is a
   test-only project never in real use, and the gate is operator-owned. Recorded
   in the issue's completion notes and a `soak_gate: waived-by-operator`
   frontmatter marker [source: .kanban/issues/023d-podium-plane-archive.md].

2. **trading Plane project archived (irreversible).** Run via
   `symphony-plane-recover archive` with typed-slug confirmation (`TRADING`).
   Target: id `201a3995-c738-4f5a-acbe-7608f302301e`, identifier `TRADING`, name
   `Crypto Trading Agents`, in the `homelab` workspace. `POST
   .../projects/<id>/archive/` → `HTTP 204`; verify read →
   `archived_at: 2026-06-11T22:42:15.516469Z`. Reversible from the Plane UI under
   archived projects [source: wiki/raw/sessions/2026-06-11-podium-023d-trading-plane-archive.md].

3. **bindings.yml cleanup.** The issue assumed a *commented-out* trading Plane
   block, but in reality only homelab's contract was commented; trading carried a
   **live** `tracker_contract` block. That live block was removed. trading keeps
   `tracker: podium` and the required `plane_project_id`, so config falls back to
   `DEFAULT_CONTRACT` (`config.py:391` returns `DEFAULT_CONTRACT` when the raw
   contract is `None`; `config.py:345` keeps `plane_project_id` required). Both
   bindings still parse [source: bindings.yml].

4. **Docs.** `web/README.md` gained a "Reverse proxy" section (Authelia
   access-control rule + reverse-proxy forward-auth snippet to expose the
   localhost-bound Podium frontend `127.0.0.1:8091` through the Authelia gate on
   `9091`), with placeholders the operator adapts to the host's actual proxy. The
   existing "Binding tracker rollback" section was updated: trading's rollback is
   retired, homelab's retained. `CONTEXT.md` marks the trading Plane project
   archived 2026-06-11, homelab Plane references intact [source: web/README.md][source: CONTEXT.md].

## Verification

- `uv run pytest` → 585 passed, 1 skipped. The single first-run failure
  (`test_podium_sqlite_concurrent`) is a pre-existing SQLite "database is locked"
  flake — passes in isolation, unrelated to these edits.
- `test_trading_binding_uses_podium_without_plane_transport` (reads the real
  `bindings.yml`) asserts trading dispatches via `PodiumTrackerAdapter` with
  `runtime.transport is None` — confirms the archive aligns with runtime: no
  Plane transport is built for trading [source: tests/test_trading_podium_dispatch.py].

## State after this session

| Item | State |
|---|---|
| trading Plane project | **archived** 2026-06-11 (reversible from Plane UI) |
| trading `tracker_contract` | removed → `DEFAULT_CONTRACT` |
| homelab Plane project | **retained**, archive deferred |
| homelab rollback contract | retained (commented block in `bindings.yml`) |
| #023d status | `in-review` (operator-pending items remain) |

## Reverse-proxy bring-up (2026-06-12)

The operator chose FQDN `https://podium.testytech.net`, proxy upstream
`10.20.20.16:8091` (LAN, not loopback). Bring-up steps done this session:

- `symphony-host.service` restarted onto #023d code (sha `82462e6`, bindings=2,
  both reconcile clean, dispatch loop alive).
- `podium-web.service` rebinding: the frontend listened on `127.0.0.1:8091`
  only (`HOST=127.0.0.1`, `start` = `next start -H ${HOST:-0.0.0.0}`), so the
  LAN proxy could not reach it. Changed the unit to `HOST=10.20.20.16` (backup
  `.bak.2026-06-12`), `daemon-reload` + restart. Verified `10.20.20.16:8091` →
  HTTP 200; loopback `127.0.0.1:8091` no longer answers; API stays loopback on
  `8090`. This exposes the unauthenticated port on the LAN — Authelia is the
  intended gate; firewall the raw port if needed (C-0109).
- DNS + reverse proxy applied by the operator.

### Still operator-pending before #023d → Done

1. Confirm `https://podium.testytech.net` loads through the Authelia gate
   end-to-end, then check the last acceptance box and move #023d to Done.

(`git commit` performed this session: `a24d229`, `82462e6` — `main` ahead,
unpushed.)

## Follow-ups

- Create the deferred homelab Plane archive issue (e.g. `023e`). The #023d
  Deferred section references it but it does not yet exist.

## Related

- [#023c homelab cutover](podium-023c-homelab-cutover.md)
- [#020 trading cutover smoke](analysis-session-020-cutover-smoke.md)
- [ADR-0005 — replace Plane with Podium](adr-0005-replace-plane-with-podium.md)
- [trading Binding](../entities/binding-trading.md)
- [symphony-* skills index](symphony-skills-index.md)
