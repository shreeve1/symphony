---
id: 087
title: "MANUAL (not Ralph) — canary claude_persist on symphony, restart, live soak"
status: pending
blocked_by: [76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86]
parent: null
priority: 0
created: 2026-06-17
---

## What to build

> ⚠️ **MANUAL OPERATOR ISSUE — DO NOT run via the Ralph loop.** This mutates live infrastructure (`bindings.yml`, `symphony-host.service`) and requires James's restart gate. Ralph must skip it. It is on the board only as the visible rollout step.

Roll the feature out on the `symphony` coding binding and verify it live.

Source: `plans/warm-claude-session-and-send-keys-steer.md` tasks 9, 12.

## What to do (manual)

- Add `claude_persist: true` to the `symphony` binding in `bindings.yml` (do NOT enable on `homelab`/infra in this change).
- Use the `symphony-restart` skill (pre-sanity → ask James → restart → verify `symphony_started`, `reconcile_startup_*`, `dispatch_completed`).
- Canary soak: route a `claude` smoke issue on the `symphony` binding (`agent:claude`); verify (a) warm reattach across a park-and-reply cycle (log shows no second ready-wait), (b) a Podium steer landing at the next turn, (c) reap on close/archive.
- Report the soak result back into issue #086 so ADR-0013 status flips to `accepted`.

## Acceptance criteria

- [ ] `bindings.yml` `symphony` binding has `claude_persist: true`; `homelab` unchanged.
- [ ] Service restarts clean (post-restart log lines present).
- [ ] Soak observes warm reattach (no second ready-wait), a landed steer, and reap on close — captured in journal evidence.

## Verification

Operator-run (NOT a Ralph automated check): `symphony-restart` skill verification log lines + manual soak observation. Gated on James for the restart and any Plane/Podium mutation.

## Blocked by

- Blocked by #76–#86 (all code + docs landed).
