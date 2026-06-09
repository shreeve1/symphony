---
title: CONTEXT.md (Symphony glossary)
type: source-summary
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - wiki/raw/symphony-context.md
  - CONTEXT.md
confidence: high
tags: [glossary, domain-language, project-overview]
---

# Source Summary — `CONTEXT.md`

## What it is

Symphony's canonical domain-language file. Defines every first-class noun the engine talks about, plus the relationships between them. Lives at the repo root and is the source of truth for naming when grilling plans, reviewing ADRs, or refactoring code [source: wiki/raw/symphony-context.md#1].

## Key entries

The glossary defines, in order: Symphony (engine), Project Binding, Mode, Agent, Workflow, Tracker Adapter, Tracker Contract, Agent Adapter, Done Marker, Verdict, Run, Run Worktree, Landing, Project Scaffold [source: wiki/raw/symphony-context.md].

Each entry follows the same shape: definition paragraph, then an `_Avoid_:` line listing deprecated or misleading synonyms.

## Why it matters

- Renames and refactors must reconcile with this file before merging.
- Plans, ADRs, and skills cite it as authority for naming.
- The "Flagged ambiguities" section is the project's open-questions backlog for vocabulary; currently empty [source: wiki/raw/symphony-context.md#71-73].

## Related wiki pages

- [Symphony engine](../concepts/symphony-engine.md) — concept page derived from this glossary
