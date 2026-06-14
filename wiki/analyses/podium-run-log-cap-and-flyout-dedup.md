---
title: Run-log size decouple + fly-out comments/context/run-summary dedup
type: analysis
status: promoted
created: 2026-06-14
updated: 2026-06-14
sources:
  - scheduler.py
  - agent_runner.py
  - web/frontend/components/IssueFlyout.tsx
  - web/frontend/components/RunDetailPanel.tsx
  - web/frontend/tests/flyout-tabs.spec.ts
  - web/frontend/tests/editing.spec.ts
  - CONTEXT.md
  - docs/adr/0007-agent-summary-as-human-comment.md
  - wiki/raw/sessions/2026-06-14-flyout-dedup-and-run-log-cap.md
confidence: high
tags: [podium, run-log, context_md, comments_md, run.summary, sanitize, truncation, flyout, pi-rpc, scheduler]
---

# Run-log size decouple + fly-out dedup

Operator-reported symptom: in the Podium issue fly-out the **comments** tab and the **context** tab showed the same text, and the run-detail pane's **summary** row was a third copy. Separately, the run-detail **Log** pane showed `## stdout … [output truncated]` — only a 2 KB tail.

## Root cause: one summary block fanned into three stores

All live bindings run `pi_mode: rpc`. `run_pi_rpc_agent` returns `"".join(assistant_parts)` as stdout, and `_assistant_delta` (`agent_runner.py:888`) keeps **only** assistant `text_delta` events — thinking and tool-call deltas are dropped. So a Run's stdout is the agent's spoken prose, which the output contract (ADR-0007) shapes as the `SYMPHONY_SUMMARY_BEGIN…END` block. Symphony fans that single block into:

| Store | What it gets | Role |
|---|---|---|
| `comments_md` | extracted summary block | human operator↔AI thread |
| `context_md` | full stdout (= the prose) wrapped in `### Symphony Context Append` | AI continuity re-feed floor + compaction substrate |
| `run.summary` | parsed summary | run-record provenance |

A terse skill (e.g. `prime`) emits only the summary block → all three coincide. A chatty agent narrating between tool calls makes `context_md` richer than `comments_md`. Verified live on `podium.db` issue 12 ("Prime", trading): `comments_md` 3866 vs `context_md` 3942 chars, same text wrapped differently [source: wiki/raw/sessions/2026-06-14-flyout-dedup-and-run-log-cap.md].

`context_md` is **not** redundant data — it is the Continuity re-feed floor and compaction substrate, and ADR-0007 leaves it deliberately unchanged. Under RPC + Session Resume it is not even injected on the resume path (the native session is authoritative). Its UI read is "incidental observability" per the [[Issue Context]] glossary. So the fix is display-only.

## Fix 1 — fly-out dedup (display-only, frontend)

- `IssueFlyout.tsx`: `TABS` → `["comments","session"]` (dropped `"context"`); removed the context render branch and the orphaned `MarkdownEditor` (its only consumer was `context_md`).
- `RunDetailPanel.tsx`: removed the `["summary", …]` row from the run-metadata grid.
- Operators inspect per-Run output via the **Run Log pane** instead. `context_md` was the only operator-editable markdown field, so that edit capability is intentionally lost (consistent with the glossary "does not normally write"). Tests updated: `flyout-tabs.spec.ts` (context→session tab), `editing.spec.ts` (context-edit test removed).
- The `context_md` store, API field/type, and seed columns are untouched — zero engine risk.

## Fix 2 — run-log size decouple (scheduler, commit `e0c02b4`, live)

Previously `_format_report` produced one `_sanitize_report(...)` result bounded to `REPORT_MAX_BYTES = 2048` (ANSI-strip + secret-redact + tail-truncate), and that same 2 KB string fed **both** `_write_run_log` and `append_context`. The run-log pane therefore only ever showed the last 2 KB tail (`... [output truncated]`), and truncation happened at write time — pre-tail content is gone from disk, not merely hidden.

Change:
- `LOG_MAX_BYTES = 1_048_576` (1 MiB) — run-log cap, decoupled from the comment/context bound.
- `_sanitize_report(text, secrets, *, max_bytes=REPORT_MAX_BYTES)` — added param; default keeps every existing caller at 2 KB.
- `_finish_run_record` drops its `stdout`/`stderr` params, takes `secrets`, and builds the log from the **raw** `result.stdout`/`result.stderr` sanitized at `LOG_MAX_BYTES`. 11 call sites updated to pass `secrets=secrets`.

Comment + `context_md` paths stay at 2 KB (compaction token budget untouched); only the run-log pane gets ~1 MiB. Secret-redaction + ANSI-strip still apply to the log. Existing logs already lost pre-2 KB content — only runs after the restart get the full tail.

### Implementation note (replace_all hazard)

The first edit used `replace_all` on the generic `stdout=stdout / stderr=stderr` kwarg pair and clobbered the unrelated `_detect_agent_schedule(stdout=, stderr=)` call (same shape). `ast.parse` and `ruff` did **not** catch it (wrong kwarg name, valid syntax). It surfaced via a call-count parity check: 12 `secrets=secrets` vs 11 `_finish_run_record` calls. Reverted. Lesson: `replace_all` on a generic kwarg pair needs a post-edit call-count parity check.

## Verification

`uv run pytest` 776 passed / 2 skipped. Restart to `code_sha=e0c02b4`; `reconcile_startup_begin/done` ×3 bindings, `run_reconcile_done reaped=0`, `dispatch_completed`, `rpc_orphan_reap_done count=0`, `pi_rpc_probe_ok`, zero errors.

## Follow-ups

- Frontend changes uncommitted at capture; Podium frontend needs `next build` + restart (or dev hot-reload) to show them; `npm run test:e2e` not yet run.
- ADR-0007 (`agent-summary-as-human-comment`) has no promoted wiki analysis page — candidate ingest opportunity.
