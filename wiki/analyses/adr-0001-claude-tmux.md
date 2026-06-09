---
title: ADR-0001 — Dispatch Claude through tmux send-keys
type: decision
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - wiki/raw/adr-0001-claude-tmux.md
  - docs/adr/0001-claude-via-tmux-send-keys.md
confidence: high
tags: [adr, claude, tmux, dispatch, verdict, done-marker]
---

# ADR-0001 — Dispatch Claude through tmux send-keys, not print mode

## Decision

Symphony dispatches agents heterogeneously: **pi** runs one-shot (`pi --print --no-session`, success from exit code), but **claude** is driven as an interactive session inside a private-socket tmux window. Prompts are pasted via `load-buffer` / `paste-buffer` + `Enter`. Completion is detected by polling `capture-pane` for a per-run nonce Done Marker [source: wiki/raw/adr-0001-claude-tmux.md#3].

## Why

Anthropic is removing usable `claude -p` (print/headless) access for this account, so the simpler one-shot path available to pi is not an option for claude [source: wiki/raw/adr-0001-claude-tmux.md#5].

## How it composes with the verdict protocol

Because a tmux session has no exit code, claude reuses the verdict protocol pi already speaks: a `SYMPHONY_RESULT: done|review|blocked` line (plus optional `SYMPHONY_SUMMARY:`) emitted before the Done Marker, backstopped by post-run side-effect inspection — commit present for `build`, plan artifact written for `plan`. This reuses the existing marker parser the rest of the pipeline already consumes rather than inventing a new vocabulary [source: wiki/raw/adr-0001-claude-tmux.md#5].

## Prior art

The engine is ported from the proven `dev-review-claude` skill rather than invented here [source: wiki/raw/adr-0001-claude-tmux.md#5].

## Related

- [ADR-0002 — Generalize Symphony](adr-0002-generalize-symphony.md)
- [Symphony engine](../concepts/symphony-engine.md) — Verdict and Done Marker sections
