---
title: ADR-0013 — Warm Claude sessions and send-keys steering
type: analysis
status: promoted
created: 2026-06-18
updated: 2026-06-18
sources:
  - wiki/raw/adr-0013-warm-claude-session-and-send-keys-steer.md
  - docs/adr/0013-warm-claude-session-and-send-keys-steer.md
  - CONTEXT.md
  - .kanban/issues/076-claude-persist-config-flag.md
  - .kanban/issues/077-claude-session-lifecycle-split-naming-sidecar.md
  - .kanban/issues/078-claude-warm-reattach.md
  - .kanban/issues/079-claude-live-steer-abort-poll-loop.md
  - .kanban/issues/080-claude-reaper-core.md
  - .kanban/issues/081-claude-reaper-scheduler-wiring.md
  - .kanban/issues/082-claude-boot-reaper-lock-gated.md
  - .kanban/issues/083-api-allow-claude-steer.md
  - .kanban/issues/084-run-end-steer-close-guard.md
  - .kanban/issues/085-frontend-claude-steer-ui.md
  - claude_runner.py
  - scheduler/__init__.py
  - config.py
  - web/api/main.py
  - web/frontend/components/IssueFlyout.tsx
  - tests/test_claude_persist.py
  - tests/test_claude_runner.py
  - tests/test_scheduler.py
  - web/api/tests/test_steer.py
  - web/frontend/tests/steer-flyout.spec.ts
confidence: high
tags: [adr, claude, tmux, warm-session, steering, claude-persist, accepted, implemented]
---

# ADR-0013 — Warm Claude sessions and send-keys steering

ADR-0013 is accepted as of 2026-06-18 after the implementation slices #076–#085 landed and passed Ralph review. It amends ADR-0010's original “pi-only live Steering / Claude park-and-reply” boundary: pi still uses RPC steering, while local Claude bindings with `claude_persist: true` can keep an issue-scoped tmux session warm and receive live steer/abort through that tmux session. Non-persist Claude remains park-and-reply only. [source: wiki/raw/adr-0013-warm-claude-session-and-send-keys-steer.md] [source: .kanban/issues/083-api-allow-claude-steer.md]

## Decision

- **Warm Session** means an issue-scoped Claude tmux session survives successful Runs and can be reattached for the next Run instead of creating a new tmux session and cold-loading `claude --resume`. The glossary now records this as conversation state only, not filesystem state. [source: CONTEXT.md] [source: .kanban/issues/078-claude-warm-reattach.md]
- **Claude Steering** uses the existing per-Run steer queue but delivers `steer` records by pasting a new turn into the warm tmux session. Claude's TUI queues that message and applies it at the next turn boundary; it does not preempt the running turn. `abort` remains the interrupt path. [source: wiki/raw/adr-0013-warm-claude-session-and-send-keys-steer.md] [source: .kanban/issues/079-claude-live-steer-abort-poll-loop.md]
- **Opt-in boundary** is the binding flag `claude_persist: true`. Default Claude behavior stays run-scoped teardown with park-and-reply between Runs. [source: .kanban/issues/076-claude-persist-config-flag.md] [source: .kanban/issues/083-api-allow-claude-steer.md]
- **Reaping** is belt-and-suspenders: run-scoped cleanup is split from session cleanup, issue terminal state and idle TTL/max-live policies reap parked sessions, and boot reaping bypasses the pid/start-time live-owner guard only when the scheduler confirms the single-instance lock. [source: .kanban/issues/077-claude-session-lifecycle-split-naming-sidecar.md] [source: .kanban/issues/080-claude-reaper-core.md] [source: .kanban/issues/081-claude-reaper-scheduler-wiring.md] [source: .kanban/issues/082-claude-boot-reaper-lock-gated.md]

## Landed slices

| Issue | Landed behavior |
|------:|-----------------|
| #076 | Added `ProjectBinding.claude_persist`, strict bool parsing, remote-binding rejection, and adapter storage. |
| #077 | Split Claude run/session lifecycle, deterministic persistent socket naming, metadata sidecar, and persist-only keepalive. |
| #078 | Added warm reattach to a live Claude socket/session with cold fallback on stale/dead/failed paste. |
| #079 | Added Claude poll-loop steer/abort handling with generation-specific result/done files and queue cleanup. |
| #080 | Added core persistent-Claude session sweep using metadata sidecars, issue liveness, idle TTL, and max-live cap. |
| #081 | Wired sweep into the scheduler poll loop for `claude_persist` bindings. |
| #082 | Lock-gated boot reaping for persistent Claude sockets. |
| #083 | Allowed `/api/issues/{id}/steer` for live Claude runs only when binding `claude_persist` is true; surfaced `claude_persist` in `/api/bindings`. |
| #084 | Closed Run rows out of `running` immediately after agent return so late steer/abort is rejected for both pi and Claude. |
| #085 | Added frontend Claude steer/abort affordance gating and Claude-specific copy. |

## ADR-0010 amendment

ADR-0010 remains correct for pi: RPC `steer` is race-free by construction and is still the preferred pi transport. ADR-0013 refines the Claude side only. The earlier wording “Claude stays tmux park-and-reply” is now “non-persist Claude stays park-and-reply; persist-enabled local Claude also supports live steer/abort through its warm tmux session.” [source: wiki/analyses/adr-0010-pi-rpc-dispatch-for-live-steering.md] [source: .kanban/issues/083-api-allow-claude-steer.md]

## Soak status

The manual canary/restart/live soak (issue #087) **PASSED 2026-06-18** on the live `symphony` binding (Podium smoke Issue #45, runs 81/82/83). All three behaviors were observed: warm reattach with no second ready-wait (`claude_dispatch resumed=true` + `claude_reattached`, 2s vs 13s cold), a Podium steer landing at the next turn (`claude_steer_delivered generation=1`), and terminal reap on close (`claude_persist_terminal_reaped state=done`). [source: .kanban/issues/087-MANUAL-canary-restart-soak.md] [source: wiki/raw/sessions/2026-06-18-claude-persist-canary-soak-087.md]

**Deployment-contract bug found and fixed during the soak (C-0242).** Live steer/abort was accepted (HTTP 200) but never delivered, because the steer queue (`$SYMPHONY_RUNTIME_DIR/steer`, default `/tmp/symphony/steer`) was not shared between the writer `podium-api.service` (`PrivateTmp=no`) and the reader `symphony-host.service` (`PrivateTmp=yes`). Fixed by setting `SYMPHONY_RUNTIME_DIR=/run/symphony` via a drop-in on both units; the steer test passed only after the fix. This invariant applies to pi RPC steering too and is unit-config-only (not enforced in code). [source: web/api/steer_queue.py] [source: docs/adr/0013-warm-claude-session-and-send-keys-steer.md] [source: CLAUDE.md]

## Claims

C-0240 and C-0242 in [CLAIMS.md](../CLAIMS.md). C-0176, C-0178, C-0193, and C-0239 are amended or refined by this ADR-0013 page.
