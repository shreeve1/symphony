---
id: 086
title: Docs, glossary, and wiki for warm Claude sessions + steering
status: review
blocked_by: [76, 77, 78, 79, 80, 81, 82, 83, 84, 85]
parent: null
priority: 0
created: 2026-06-17
---

## What to build

Land the documentation for the shipped behaviour: CONTEXT.md glossary terms, ADR-0013 status, and the wiki (candidate → lint → promote, plus CLAIMS amendment). This runs last so it describes behaviour that actually exists.

Source: `plans/warm-claude-session-and-send-keys-steer.md` tasks 11.1–11.4.

## What to build (detail)

- `CONTEXT.md` `Steering` term (`:104`): add the Claude clause (send-keys append-next-turn; abort = interrupt) and revise its `_Avoid_: "send-keys"` line (send-keys is now the accepted Claude steer mechanism, distinct from pi RPC).
- Add a `CONTEXT.md` `Warm Session` term: issue-scoped Claude tmux; reattach; reaped on done/archived, parked-idle-TTL, max-live cap, and lock-gated boot.
- ADR-0013: set status `proposed` → `accepted` and record the soak result (mirror ADR-0010's `slice-a-soak` line). (The soak itself is issue #087; this task only records it once #087 reports.)
- Wiki: create `wiki/candidates/adr-0013-warm-claude-and-send-keys-steer.md`, lint, auto-promote to `wiki/analyses/`; amend `C-0176`/ADR-0010 in `wiki/CLAIMS.md`; update `wiki/index.md`, `wiki/ROUTING.md`, append `wiki/log.md`.

## Acceptance criteria

- [ ] `CONTEXT.md` contains a `Warm Session` term and a Claude clause in `Steering`; the stale `_Avoid_: send-keys` framing is revised.
- [ ] A promoted `wiki/analyses/adr-0013-*.md` exists with `status: promoted`; `wiki/index.md`, `wiki/ROUTING.md`, `wiki/log.md` reference it; `wiki/CLAIMS.md` marks the `C-0176`/ADR-0010 amendment.
- [ ] No broken wikilinks introduced (lint passes).

## Verification

`grep -q "Warm Session" CONTEXT.md && grep -q "adr-0013" wiki/index.md wiki/ROUTING.md && grep -q "0013" wiki/CLAIMS.md && test -f wiki/analyses/adr-0013-warm-claude-and-send-keys-steer.md`

## Blocked by

- Blocked by #76–#85 (documents the complete shipped behaviour).
