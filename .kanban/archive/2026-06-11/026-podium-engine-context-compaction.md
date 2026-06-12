---
id: 026
title: Engine-built context compaction (Symphony invokes configured agent)
status: done
blocked_by: [020]
updated: 2026-06-11
actor: ralph
parent: null
priority: 0
created: 2026-06-10
---

## What to build

Per ADR-0005 ¶3 and CONTEXT.md `[[Issue Context]]`: when an issue's
`context_md` exceeds a per-binding token threshold, Symphony invokes the
configured agent with a hardcoded compaction prompt before dispatching
the operator's Run. Not a Skill; no Run row produced.

Mechanics:

1. New module `context_compaction.py` exposes
   `maybe_compact(issue, binding, agent_runner) -> str` returning the
   (possibly updated) `context_md`.
2. Threshold lives on `binding_settings.context_compact_threshold_tokens`
   (default 16000). Token count uses a simple heuristic
   (`len(text) // 4`) for v1 — accurate enough for the threshold
   decision; no tokenizer dependency.
3. When the threshold is exceeded, Symphony:
   - Builds a prompt from a hardcoded template
     (`context_compaction.COMPACTION_PROMPT`).
   - Invokes the configured agent (`agent_runner.run_agent`) with the
     prompt and the current `context_md` as input.
   - Parses the agent's output (looks for a `SYMPHONY_COMPACTED_CONTEXT:`
     marker block).
   - Prepends a marker line to the new compacted blob:
     `<!-- context compacted on <iso8601>, trimmed N→M tokens -->`.
   - Writes the result back via `tracker.append_context(...)` (or a
     dedicated `replace_context(...)` method on the adapter — preferred
     because compaction *replaces*, not appends).
4. Compaction is invoked from the dispatch path BEFORE the operator's
   Run starts. The operator Run sees the compacted context.
5. No `run` row is created for compaction. No `skill_invoked` value. No
   UI surfacing beyond the marker line inside `context_md` itself.
6. Operator can trigger compaction manually via `POST /api/issues/{id}/compact`
   (calls the same engine function).

Settings to add to `binding_settings`:
- `context_compact_threshold_tokens INTEGER DEFAULT 16000`
- `context_compact_keep_recent_runs INTEGER DEFAULT 3` (read by the
  prompt template; "keep last N Runs verbatim").

## Acceptance criteria

- [x] `context_compaction.py` exists; `maybe_compact(...)` is unit-tested for: below-threshold (no-op), above-threshold (invokes agent), agent error (raises and does NOT corrupt `context_md`), missing marker in agent output (raises).
- [x] Alembic revision adds `context_compact_threshold_tokens` and `context_compact_keep_recent_runs` to `binding_settings`.
- [x] Hardcoded `COMPACTION_PROMPT` instructs the agent to (a) summarize Runs older than `keep_recent_runs`, (b) preserve the last N Runs verbatim, (c) preserve operator-edited instruction blocks, (d) emit `SYMPHONY_COMPACTED_CONTEXT:` marker.
- [x] Dispatch path calls `maybe_compact` before invoking the operator's agent; covered by `tests/test_dispatch_compaction.py`.
- [x] No `run` row created during compaction (assert by row count delta in test).
- [x] `POST /api/issues/{id}/compact` triggers the same flow synchronously and returns the new token count.
- [x] Marker line `<!-- context compacted on ... -->` rendered at top of compacted `context_md`.
- [x] Agent invocation uses `binding.default_agent` / `binding.default_model` (not hardcoded to pi — the configured agent per ADR-0005).

## Verification

```
cd /home/james/symphony && uv run pytest
```

## Implementation Notes

Implemented engine-owned Podium Issue Context compaction before operator dispatch. Added `context_compaction.py`, a `binding_settings` migration/table, Podium `replace_context(...)` and settings lookup methods, scheduler pre-run compaction, and `POST /api/issues/{id}/compact`. Verification passed with `uv run pytest` (563 passed, 1 skipped), fresh review passed, and touched-file LSP diagnostics reported no errors.

## Blocked by

- #020 (real engine dispatch must exist before compaction layers into the dispatch path)
