---
id: 087
title: "MANUAL (not Ralph) — canary claude_persist on symphony, restart, live soak"
status: done
updated: 2026-06-18
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

- [x] `bindings.yml` `symphony` binding has `claude_persist: true`; `homelab` unchanged.
- [x] Service restarts clean (post-restart log lines present).
- [x] Soak observes warm reattach (no second ready-wait), a landed steer, and reap on close — captured in journal evidence.

## Soak result (2026-06-18)

PASSED on live `symphony` binding. Podium smoke Issue #45 (`agent:claude`, `claude-opus-4-8`), runs 81/82/83.

- **Config:** `claude_persist: true` on `symphony` only, committed `ce07042`; `homelab` untouched.
- **Restart:** clean — `symphony_started code_sha=ce07042 bindings=4`, reconciles 4/4/0, `pi_rpc_probe_ok`, 0 errors (PID 3167775 @ 03:09:51 UTC).
- **(a) warm reattach:** turn 2 `claude_dispatch resumed=true` + `claude_reattached socket=/tmp/symphony-claude-persist-symphony-45.sock`, no second ready-wait (2s vs 13s cold).
- **(b) steer lands next turn:** `claude_steer_delivered issue_id=45 kind=steer generation=1`; run-83 result carried the steered line `steer landed turn3`.
- **(c) reap on close:** issue → `done` → `claude_persist_terminal_reaped issue_id=45 state=done`; socket + tmux session removed.

**Bug found + fixed during soak:** live steer/abort was broken in deployment — `podium-api.service` (queue writer, `PrivateTmp=no`) and `symphony-host.service` (queue reader, `PrivateTmp=yes`) did not share `/tmp/symphony/steer`; steers got HTTP 200 but were never delivered (also affected pi RPC). Fixed by `SYMPHONY_RUNTIME_DIR=/run/symphony` drop-in on both units. Step (b) passed only after the fix. Recorded in ADR-0013 `soak:` line, `CLAUDE.md` "Env locations", and #086. ADR-0013 status confirmed `accepted`.

## Verification

Operator-run (NOT a Ralph automated check): `symphony-restart` skill verification log lines + manual soak observation. Gated on James for the restart and any Plane/Podium mutation.

## Blocked by

- Blocked by #76–#86 (all code + docs landed).
