---
title: Podium #026 — engine-built Issue Context compaction
type: analysis
status: promoted
created: 2026-06-11
updated: 2026-06-11
sources:
  - context_compaction.py
  - scheduler.py
  - tracker_podium.py
  - web/api/main.py
  - web/api/schema.py
  - web/api/migrations/versions/0002_context_compaction_settings.py
  - tests/test_context_compaction.py
  - tests/test_dispatch_compaction.py
  - web/api/tests/test_context_compaction.py
confidence: high
tags: [podium, context-compaction, scheduler, issue-context, alembic]
---

# Podium #026 — engine-built Issue Context compaction

## Summary

#026 lands engine-owned Podium Issue Context compaction. When a Podium Issue's `context_md` exceeds the configured token threshold, Symphony invokes the configured runtime agent before creating the operator Run, parses a `SYMPHONY_COMPACTED_CONTEXT:` marker, replaces `context_md`, and only then renders the operator prompt. [source: context_compaction.py] [source: scheduler.py]

## Compaction contract

`context_compaction.py` defines the v1 token estimate as `len(text) // 4`, a default threshold of 16,000 tokens, and default `keep_recent_runs=3`. `maybe_compact(...)` no-ops below threshold, calls the supplied agent runner above threshold, raises without returning replacement text on agent timeout/non-zero/missing marker/empty output, and prepends a marker line of the form `<!-- context compacted on <iso8601>, trimmed N→M tokens -->` to stored compacted context. [source: context_compaction.py] [source: tests/test_context_compaction.py]

`COMPACTION_PROMPT` tells the agent to summarize older Runs, preserve the last N Runs verbatim, preserve operator-edited instruction blocks, preserve durable decisions/blockers/terminology, remove duplicated transient logs, and emit `SYMPHONY_COMPACTED_CONTEXT:` followed by markdown. [source: context_compaction.py]

## Dispatch integration

`scheduler.run_tick(...)` calls `_maybe_compact_context(...)` before prompt rendering and before `_start_run_record(...)`, so compaction does not create a `run` row or `skill_invoked` value. Since #043, compaction uses a separate `compaction_agent_runner` and resolves the Pi catalog default, so engine housekeeping stays Pi-only even when the operator dispatch routes to Claude. On safe compaction errors, the Issue moves to Blocked with a `Context compaction failed: ...` comment and no Run row is created. [source: scheduler.py] [source: tests/test_dispatch_compaction.py] [source: wiki/analyses/podium-043-claude-dispatch-routing.md]

The dispatch regression test configures a tiny threshold, verifies the first agent call is the compaction prompt, verifies the second call is the operator prompt containing compacted context, and asserts `SELECT COUNT(*) FROM run` equals 1 after the operator Run. A failure-path test asserts failed compaction blocks the Issue, leaves original `context_md` unchanged, and creates zero Run rows. [source: tests/test_dispatch_compaction.py]

## Podium persistence and API

Podium now has a `binding_settings` table with `context_compact_threshold_tokens INTEGER DEFAULT 16000` and `context_compact_keep_recent_runs INTEGER DEFAULT 3`. Runtime `SCHEMA_SQL` and Alembic head both include revision `0002_context_compaction_settings`, and `ensure_schema(...)` updates `alembic_version` to the current runtime revision for schema-created DBs. [source: web/api/schema.py] [source: web/api/migrations/versions/0002_context_compaction_settings.py] [source: web/api/main.py] [source: tests/test_alembic_baseline.py]

`PodiumTrackerAdapter` adds `replace_context(...)` for true replacement semantics and `context_compaction_settings(...)` for per-binding threshold/keep values, falling back to defaults if no settings row exists. [source: tracker_podium.py]

`POST /api/issues/{id}/compact` runs the same compaction flow synchronously and returns `issue_id`, `compacted`, and `token_count`. Endpoint tests cover success and missing-Issue 404. [source: web/api/main.py] [source: web/api/tests/test_context_compaction.py]

## Design correction

ADR-0005 described Issue Context compaction as having "zero schema impact." The implementation corrected that: per-binding threshold and keep settings require the new `binding_settings` table. Treat the ADR phrase as design-era superseded detail, not current implementation truth. [source: wiki/analyses/adr-0005-replace-plane-with-podium.md] [source: web/api/schema.py]

## Verification

Implementation verification passed with `uv run pytest`: 563 passed, 1 skipped. Touched-file LSP diagnostics reported no errors. Fresh review inspected `git diff 981a2e9501af261ca56744edcef06c68fc73345a HEAD`, read every changed file, ran `uv run pytest`, compiled touched Python files, confirmed clean git status, and returned `RALPH_REVIEW: PASS`.

## Claims

C-0095 .. C-0098 in [CLAIMS.md](../CLAIMS.md).
