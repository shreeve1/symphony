# Symphony LLM Wiki

LLM-maintained knowledge base for the Symphony host-native scheduler: binding lifecycle, dispatch loop, Plane integration, troubleshooting patterns, and operational runbooks.

## Rules

- `raw/` is immutable source material.
- `candidates/` is a transient holding area; this project uses **auto-promotion** — the agent self-reviews and promotes after lint passes (no James gate).
- Promoted pages must be indexed in `index.md`; candidates must appear only in the candidate review queue while transiting.
- Important factual claims must be tracked in `CLAIMS.md`.
- All changes must be logged in `log.md`.
- Citation style: inline `[source: path/to/file.md#section]`.

## Workflows

- Ingest: add source to `raw/`, summarize, extract claims, create candidate, lint, auto-promote, update index/routing/claims/log.
- Session update: use `/wiki-update` to capture durable decisions, verified facts, and follow-ups from a session into raw session notes, candidates (auto-promoted), claims, routing, index, and log.
- Query: read `index.md`, optionally use `ROUTING.md` to narrow scope, then read relevant promoted pages; cite sources.
- Lint: check broken links, orphan pages, stale claims, claim drift against cited sources, duplicates, missing concept pages, data gaps, contradictions.
- Promote: agent self-promotes; move candidate to final location, update index/routing/claims/log.
- Discard: remove stale candidate index rows, candidate routes, and candidate claim references, then log the discard.
