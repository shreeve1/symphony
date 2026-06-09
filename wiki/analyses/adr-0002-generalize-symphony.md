---
title: ADR-0002 — Generalize Symphony behind adapter seams
type: decision
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - wiki/raw/adr-0002-generalize-symphony.md
  - docs/adr/0002-generalize-symphony-over-adopting-a-platform.md
confidence: high
tags: [adr, architecture, adapter, tracker-adapter, agent-adapter, build-vs-buy, sortie]
---

# ADR-0002 — Generalize Symphony behind adapter seams, rather than adopt an existing orchestrator

## Decision

Keep and generalize Symphony, introducing two explicit seams — a **Tracker Adapter** (isolating Plane) and an **Agent Adapter** (isolating pi vs claude dispatch). Borrow proven conventions from sortie (per-repo `WORKFLOW.md` front-matter-plus-template shape, tracker/agent adapter-interface boundaries) rather than its code [source: wiki/raw/adr-0002-generalize-symphony.md#5].

## Alternatives evaluated

Off-the-shelf platforms considered: sortie, Composio Agent Orchestrator, Warren/overstory, Code Conductor, GitHub Agent HQ [source: wiki/raw/adr-0002-generalize-symphony.md#3].

## Why not adopt a platform

The decisive constraint is that every mature platform assumes the coding agent runs **headless** (`claude -p`, stdio, NDJSON). This account is losing usable headless Claude and is forced into tmux send-keys (see [ADR-0001](adr-0001-claude-tmux.md)). Adopting any platform would therefore still require writing a custom tmux agent adapter — the hardest, most unusual part — on top of writing a Plane tracker adapter and giving up working Python (sortie is Go). The two things that make this setup ours (Plane, pi) are unsupported or niche everywhere: only the now-archived overstory line ever ran pi, and no platform speaks Plane. Net: adopting reimplements nearly everything to gain nearly nothing [source: wiki/raw/adr-0002-generalize-symphony.md#7].

## Validation, not capitulation

That sortie independently converged on Symphony's exact architecture (poll-by-label → render per-issue template → isolated workspace → dispatch → reconcile state) is treated as validation of the design, not a reason to switch [source: wiki/raw/adr-0002-generalize-symphony.md#9].

## Long-term hedge

The adapter seams are the long-term hedge: if Plane or pi is ever abandoned, swap one adapter instead of rewriting the engine. Self-hosted Plane is kept now for privacy over the local infra repo, accepting that no ecosystem tooling will ever target Plane [source: wiki/raw/adr-0002-generalize-symphony.md#9].

## Related

- [ADR-0001](adr-0001-claude-tmux.md) — tmux constraint that drives this
- [ADR-0004](adr-0004-tracker-contract.md) — concrete shape of the Tracker Adapter seam
- [Symphony engine](../concepts/symphony-engine.md)
