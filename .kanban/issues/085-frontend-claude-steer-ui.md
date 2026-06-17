---
id: 085
title: Frontend — gate steer/abort on active-run agent, Claude append-vs-interrupt copy
status: pending
blocked_by: [83]
parent: null
priority: 0
created: 2026-06-17
---

## What to build

Enable the Podium flyout steer textarea + abort button for live Claude runs on `claude_persist` bindings, gated on the ACTIVE RUN's agent (not just the binding flag), and render Claude-specific copy that distinguishes steer (append, acts next turn) from abort (interrupt now).

Source: `plans/warm-claude-session-and-send-keys-steer.md` tasks 8.1–8.4.

## What to build (detail)

- Add `claude_persist?: boolean` to the binding type in `web/frontend/lib/api.ts` (sibling to `pi_mode`).
- In `IssueFlyout.tsx` (current gate `latestRunAgent === "pi" && bindingPiMode === "rpc"`, ~`:475-490`), change to: `liveRun && ((latestRunAgent === "pi" && bindingPiMode === "rpc") || (latestRunAgent === "claude" && bindingClaudePersist))`. This prevents showing Claude steer for a pi one-shot run on a `claude_persist` binding.
- When the active run's agent is Claude, render copy: steer = "queued; Claude picks it up at its next turn" (append, not interrupt); abort = "interrupt the current turn now (Esc)". Keep pi RPC copy unchanged.

## Acceptance criteria

- [ ] Steer/abort controls appear for a live Claude run on a `claude_persist` binding; hidden/disabled for a pi one-shot run on the same binding.
- [ ] pi RPC gating + copy unchanged.
- [ ] Claude copy distinguishes append-next-turn steer from interrupt abort.
- [ ] `claude_persist` is read from the binding payload (`/api/bindings`).

## Verification

`cd web/frontend && pnpm test:e2e tests/steer-flyout.spec.ts` (extend the spec for the Claude/claude_persist case)

## Blocked by

- Blocked by #83 (`/api/bindings` exposes `claude_persist`).
