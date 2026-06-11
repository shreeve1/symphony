# Session Capture: Podium #023d — trading Plane archive + reverse-proxy docs

- Date: 2026-06-11
- Purpose: Execute kanban issue #023d (descoped to trading-only), archiving the
  trading Plane project after the operator waived the one-week soak gate, and
  drafting the Authelia reverse-proxy documentation. Homelab Plane archive was
  deferred to a follow-up.
- Scope: Captured the gate-override decision, the irreversible Plane archive,
  the `bindings.yml` / `CONTEXT.md` / `web/README.md` edits, and the
  operator-pending remainder.

## Durable Facts

- The `trading` Plane project (id `201a3995-c738-4f5a-acbe-7608f302301e`,
  identifier `TRADING`, name `Crypto Trading Agents`, in the `homelab`
  workspace) was archived 2026-06-11 via `symphony-plane-recover archive` after
  typed-slug confirmation. `POST .../projects/<id>/archive/` returned `HTTP 204`;
  verify read showed `archived_at: 2026-06-11T22:42:15.516469Z`. Reversible from
  the Plane UI under archived projects. — Evidence: `symphony-plane-recover` skill run; Plane API `archived_at`.
- The trading binding's live (uncommented) `tracker_contract` block was removed
  from `bindings.yml`. The issue text had assumed it was a commented rollback
  block; in reality only homelab's block was commented. trading keeps
  `tracker: podium` and required `plane_project_id`; with no contract it falls
  back to `DEFAULT_CONTRACT`. — Evidence: `bindings.yml`, `config.py:391` (`raw is None` → `DEFAULT_CONTRACT`), `config.py:345` (`plane_project_id` required).
- Both bindings still parse after the edit; `test_trading_binding_uses_podium_without_plane_transport`
  confirms trading dispatches via Podium with no Plane transport. `uv run pytest`
  → 585 passed, 1 skipped (lone `test_podium_sqlite_concurrent` failure is a
  pre-existing SQLite-lock flake; passes in isolation). — Evidence: `tests/test_trading_podium_dispatch.py:258`, pytest run.
- `web/README.md` gained a "Reverse proxy" section documenting the Authelia
  access-control rule + reverse-proxy forward-auth snippet to expose the
  localhost-bound Podium frontend (`127.0.0.1:8091`) through the Authelia gate
  on `9091`. Snippet uses placeholders; the operator adapts it to the host's
  actual proxy and applies it (outside this repo). The "Binding tracker
  rollback" section now records trading's rollback retired, homelab's retained.
  — Evidence: `web/README.md` (Reverse proxy + Binding tracker rollback sections).
- `CONTEXT.md` Tracker Adapter entry now notes the trading Plane project was
  archived 2026-06-11; homelab Plane references left intact. — Evidence: `CONTEXT.md` Tracker Adapter entry.

## Decisions

- **Soak gate waived for trading.** James directed overriding the issue's
  one-week Podium soak gate: trading is a test-only project never in real use.
  The gate is operator-owned; recorded in #023d completion notes in lieu of a
  "soak passed" timestamp. — Evidence: session; `.kanban/issues/023d-podium-plane-archive.md` (Completion notes, `soak_gate: waived-by-operator`).
- **Homelab archive deferred.** #023d was descoped to trading-only. Homelab
  stays on Plane (rollback contract + project retained) until a follow-up issue
  archives it under the same ritual. — Evidence: `.kanban/issues/023d-podium-plane-archive.md` (Deferred section).
- **No service restart, no git commit performed.** The bindings change is inert
  for the podium path and parses cleanly; restart deferred to operator
  convenience via `symphony-restart`. Commit left to operator. — Evidence: session.

## Evidence

- `.kanban/issues/023d-podium-plane-archive.md` — descoped issue + completion notes + transcript.
- `bindings.yml` — trading `tracker_contract` removed, replaced with a dated comment.
- `config.py:345,391` — `plane_project_id` required; `None` contract → `DEFAULT_CONTRACT`.
- `web/README.md` — Reverse proxy section; updated rollback section.
- `CONTEXT.md` — trading Plane archive marker.
- `tests/test_trading_podium_dispatch.py:258` — trading-uses-podium-without-plane test.

## Exclusions

- `/home/james/symphony-host.env` contents (PLANE_API_KEY) never printed; only key length echoed during env sourcing.
- No full transcript captured.

## Open Questions And Follow-Ups

- Create the deferred homelab Plane archive follow-up issue (e.g. `023e`); the
  #023d Deferred section references it but it does not yet exist.
- Operator-pending before #023d → Done: apply the Authelia/reverse-proxy rule
  and reload the proxy, then confirm Podium reachable through the Authelia gate.
- No git commit yet for the #023d working-tree changes.
