# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root, or
- **`CONTEXT-MAP.md`** at the repo root if it exists — it points at one `CONTEXT.md` per context. Read each one relevant to the topic.
- **`docs/adr/`** — read ADRs that touch the area you're about to work in. In multi-context repos, also check `src/<context>/docs/adr/` for context-scoped decisions.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

Single-context repo (most repos):

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

Multi-context repo (presence of `CONTEXT-MAP.md` at the root):

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← system-wide decisions
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← context-specific decisions
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders) — but worth reopening because…_

## Symphony-specific reading order

Symphony already has a richer knowledge base than `CONTEXT.md` alone — read these in order before going to the codebase:

1. `wiki/index.md` — the wiki is the **primary** knowledge base for scheduler internals, runbooks, decisions, and operational patterns. Per `CLAUDE.md` ("Wiki-First Project Search"), prefer it over the codebase.
2. `wiki/ROUTING.md` — narrow large searches.
3. `wiki/CLAIMS.md` — atomic claims, with inline citations.
4. `CONTEXT.md` — the canonical domain glossary (uses `[[wikilinks]]` to other concepts; resolve them by walking the file or grepping for the term).
5. `docs/adr/` — concrete decisions. Cross-reference with `wiki/concepts/` where the same decision has both a wiki concept page and an ADR.
6. `~/homelab/docs/runbooks/automation/symphony.md` — operational runbook.

Don't re-search the codebase for things already settled in the wiki.