---
title: ADR-0005 — Replace Plane with Podium (Symphony-native tracker + operator console)
type: decision
status: promoted
created: 2026-06-10
updated: 2026-06-10
sources:
  - wiki/raw/adr-0005-replace-plane-with-podium.md
  - docs/adr/0005-replace-plane-with-podium.md
confidence: high
tags: [adr, podium, plane-retirement, tracker-adapter, run-table, skill, worktree-opt-in, binding-is-project, sqlite]
---

# ADR-0005 — Replace Plane with Podium

Decision record. Retires Plane; builds Podium, a Symphony-native tracker + operator console. Dense fact map for future sessions; read alongside [concepts/podium-tracker.md](../concepts/podium-tracker.md) for live schema/code grounding.

## Decision (one line)

Build **Podium** (FastAPI:8090 + Next.js App Router:8091, SQLite `/var/lib/symphony/podium.db`, Alembic) as Plane's replacement; Plane archived after both bindings cut over [source: wiki/raw/adr-0005-replace-plane-with-podium.md#5].

## Why now — the four frictions that killed Plane

1. **Label-as-semantics leak.** Engine behavior encoded in tracker tags (`mode:plan`, `mode:build`, `agent:pi`, `approval-required`, `approved`, `scheduled`) — right lever inside a tracker we don't own, wrong lever once we own the store.
2. **Round-trip cost.** Every engine-significant operator action = a Plane API write + a per-binding UUID map kept in sync.
3. **Mixed streams.** Comments and AI session logs share one Plane comment stream; reading either is noisy.
4. **No operator-lever home.** No native place for per-Issue agent override, model override, worktree opt-in.
[source: wiki/raw/adr-0005-replace-plane-with-podium.md#3]

Compounding context: thin engine v2 (`e73e924`) already deleted worktree-per-Run, the Claude tmux adapter, plan→build handoff, and Landing for coding bindings. Live binding split: `trading` = `coding` (no schedule/reconciler/approval/worktree, agent owns git); `homelab` = `infra` (still exercises schedule + blocked-reconciler + approval paths; worktree mechanism deleted at module level for both) [source: wiki/raw/adr-0005-replace-plane-with-podium.md#3].

## Architecture deltas (Plane → Podium)

| Concept | Plane era | Podium |
|---|---|---|
| Project layer | separate Plane Project per binding | **dropped** — Binding *is* the Project (nothing else writes the project layer) |
| Run | implicit; reconciled from durable signals | **first-class table**, one row per dispatch, mutable state machine, log → `runs/{id}.log`, no event-log table v1 |
| Operator levers | labels + UUID maps | **typed columns**: `preferred_agent/model/skill`, `reasoning_effort` (def high), `worktree_active` (def false), `max_duration_seconds`, `base_branch` |
| Work-shape lever | **Mode** (plan/build/execute) | **Skill** — catalog (`skill` table, CLI-refreshed) + per-Issue `preferred_skill` + per-Run `skill_invoked`. Skill subsumes Mode entirely |
| Comments | one stream | `comments_md` (bidirectional human↔AI; humans full, AI concise) + `context_md` (AI-only session log; AI full write, AI read on dispatch) |
| Context overflow | n/a | engine-built compaction: when `context_md` > threshold, Symphony runs configured agent w/ hardcoded compaction prompt — not a Skill, zero schema impact |
| Worktrees | engine-default per-Run (ADR-0003) | **opt-in per-Issue persistence**: false → run in repo checkout (thin engine v2 behavior); true → persistent per-Issue branch+worktree, FF-merge to base on Issue→Done then teardown |
[source: wiki/raw/adr-0005-replace-plane-with-podium.md#5]

## Run table latest-projection (board reads cheap)

Issue carries `latest_run_id`, `latest_verdict`, `latest_run_state`, `last_event_at` so the board renders without joining Run [source: wiki/raw/adr-0005-replace-plane-with-podium.md#5].

## Startup reaper

On Symphony startup, any Run still `queued` or `running` → reaped to synthetic `failed`/`blocked` verdict + `restart-orphan` summary, so the board reflects reality after a crash/restart. Replaces the in-memory reconcile-from-durable-signals model (ADR-0003 C-0019) since Podium now has a DB [source: wiki/raw/adr-0005-replace-plane-with-podium.md#5].

## Worktree opt-in merge policy (true case)

Issue→Done with `worktree_active=true` → FF-merge per-Issue branch to base, teardown worktree. Conflict / diverged base / force-pushed base → **abort merge, leave worktree intact, post blocked comment**. No merge-commit fallback, no force-push, no rebase [source: wiki/raw/adr-0005-replace-plane-with-podium.md#5].

## Tracker Adapter seam carries both

`bindings.yml` gains `tracker: plane|podium`. Both satisfy ADR-0004's role contract by *different mechanisms*: Plane resolves Roles → label/state names + UUIDs; Podium projects Roles directly onto typed columns (`mode:*` + `approval-required`/`approved`/`scheduled` fold into columns or disappear; `agent:*` → `preferred_agent`; five states stay as enum). ADR-0004's role-as-engine-interface **stands**; its Plane-shaped contract is **partially superseded** for the Podium impl [source: wiki/raw/adr-0005-replace-plane-with-podium.md#5].

## Service topology

`symphony-host.service` unchanged. Adds two sibling units — `podium-api.service`, `podium-web.service` — each with own `OnFailure=telegram-alert@%n.service` so the three processes fail/restart independently. Both Podium ports bind localhost; external access via existing Authelia reverse proxy on 9091. Auth = single bcrypt-hashed shared password `PODIUM_PASSWORD_HASH` from `/home/james/symphony-host.env` (single-user, James only). WebSocket pushes Run-state + Issue-field changes; clients reconcile from row state on reconnect [source: wiki/raw/adr-0005-replace-plane-with-podium.md#5].

Landed state: #023a installed and enabled `podium-api.service` and `podium-web.service`; API runs uvicorn on `127.0.0.1:8090` with `--workers 1`, web runs Next.js on `127.0.0.1:8091` via `HOST=127.0.0.1`, and both load `/home/james/symphony-host.env` [source: wiki/raw/podium-api.service; wiki/raw/podium-web.service]. Failure notification is wired through `telegram-alert@.service` and `/usr/local/sbin/send-telegram-systemd-alert`; unattended review verifies this wiring without firing live Telegram alerts [source: wiki/raw/telegram-alert@.service; wiki/raw/send-telegram-systemd-alert; .kanban/issues/023a-podium-systemd-units.md].

## Migration

Fresh stand-up per binding (no data migration): **trading first** (disposable PoC repo), then **homelab** after Podium tuned. Plane archived after both cut over. Clean cutover per binding → brief window per binding where neither tracker is authoritative; acceptable (trading disposable, homelab single-operator) [source: wiki/raw/adr-0005-replace-plane-with-podium.md#5,11].

## Rejected alternatives (each with concrete reason)

- **Stay on Plane** — preserves all four frictions. The exact things that drove the decision.
- **Third-party platform** (sortie, Composio, Warren, Code Conductor, Agent HQ) — ADR-0002 already rejected; calculus unchanged: all assume headless Claude (abandoned), none speak Plane, still need custom tracker + agent adapters (the hard parts).
- **UI shell over Plane** — dissolves label-semantics visually but not structurally; DB still Plane's, levers still Plane writes, UUID maps still maintained.
- **Two-entity Project + Binding schema** — re-creates the Plane drift Podium escapes.
- **Event-log-only Run model** — clean audit/replay, but pays off only with multi-user/post-hoc analysis; single-user v1 reconciles from row state on reconnect.
- **Keep Mode + add Skill** — two parallel work-shape levers; Skill subsumes Mode (catalog-driven, per-binding customizable, already where tuning energy goes).
- **Plane→Podium data migration tool** — burns budget on data neither binding cares about.
[source: wiki/raw/adr-0005-replace-plane-with-podium.md#7]

## ADR-0002 reconciliation

**Stands**: Tracker Adapter seam (structural reason swap is cheap; Podium = 2nd impl), Agent Adapter seam (pi-only post-thin-engine but the long-term hedge), Workflow concept (`WORKFLOW.md` per binding unchanged), the sortie-convergence validation framing. **Overridden**: ADR-0002's "stay on self-hosted Plane for privacy" — Podium is also self-hosted (same host/network), removes the Plane process and the UUID-map burden [source: wiki/raw/adr-0005-replace-plane-with-podium.md#9].

## ADR-0001 / ADR-0003 status

Neither *reversed* by ADR-0005 — thin engine v2 already deleted both mechanisms at module level. ADR-0003: Podium's `worktree_active` opt-in is the lever that reintroduces worktrees as an **operator-controlled** feature, not an engine default — the meaningful posture shift. ADR-0001: `preferred_agent` column keeps the door open to re-add a Claude adapter against the same seam if the headless story changes [source: wiki/raw/adr-0005-replace-plane-with-podium.md#9].

## Known bug flagged (out of ADR scope)

`scheduler.py:488` keys `is_coding` off `bindings[0].binding_type` alone → the whole `is_coding` branch resolves against whichever binding is first in `bindings.yml`, not per-issue. Flagged for cleanup [source: wiki/raw/adr-0005-replace-plane-with-podium.md#3; scheduler.py:488].

## Accepted costs

Two new systemd units; Node + browser toolchain for Playwright screen-level tests alongside pytest; `/var/lib/symphony/podium.db` whose loss erases Run history + Issue Context + Comments → added to host backup chain (rsnapshot of `/var/lib/symphony/`), off-host replication absence acknowledged as single-user posture's weakness. Run logs `runs/{id}.log`: rolling 90-day window, capped 100 most-recent per Issue, whichever cuts first. Single-shared-password auth bakes single-user assumption in; multi-user explicit non-goal; loopback-behind-Authelia bounds the auth weakness to a host-LAN attacker already past the proxy. Plane-coupled skill suite migrates: `symphony-project-scaffold`, `symphony-binding-smoke`, `symphony-bindings-status`, `symphony-plane-recover`, `symphony-onboard-project` either retire (Plane-only) or grow Podium counterparts; `symphony-workflow-author` becomes tracker-agnostic (edits `WORKFLOW.md`, not the tracker). WORKFLOW.md tuning becomes migration work: label-semantics routing → column-semantics routing. CONTEXT.md must retire Mode, Run Worktree's Plane-era framing, and Landing-via-merge when Podium ships [source: wiki/raw/adr-0005-replace-plane-with-podium.md#11].

## Claims

C-0059 .. C-0067 and C-0103 in [CLAIMS.md](../CLAIMS.md). Supersession note added to C-0004 (Mode plan/build/execute → Podium drops Mode for Skill).
