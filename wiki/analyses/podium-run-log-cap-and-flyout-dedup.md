---
title: Run-log size decouple + fly-out comments/context/run-summary dedup
type: analysis
status: promoted
created: 2026-06-14
updated: 2026-06-24
sources:
  - scheduler.py
  - agent_runner.py
  - web/frontend/components/IssueFlyout.tsx
  - web/frontend/components/Markdown.tsx
  - web/frontend/components/RunDetailPanel.tsx
  - web/frontend/tests/flyout-tabs.spec.ts
  - web/frontend/tests/steer-flyout.spec.ts
  - web/frontend/tests/global-setup.mjs
  - web/frontend/tests/editing.spec.ts
  - CONTEXT.md
  - docs/adr/0007-agent-summary-as-human-comment.md
  - wiki/raw/sessions/2026-06-14-flyout-dedup-and-run-log-cap.md
  - wiki/raw/sessions/2026-06-16-flyout-comment-ordering.md
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

## Follow-on (2026-06-16) — comment thread ordering + single-blob render

A later session reworked the same `CommentsThread` component again. The #014-era version split `comments_md` on any heading (`splitCommentEntries`, regex `/\n(?=#{1,6} )/g`), wrapped each fragment in a `comment-entry` card, and rendered **newest-first** (`.reverse()`). Two problems: (1) the operator found newest-first hard to follow; (2) the `#{1,6}` split shredded any `### Symphony AI Summary` that contained sub-headings into multiple out-of-order cards.

Fix (display-only, `IssueFlyout.tsx`): render `comments_md` as a single `<Markdown>` block inside one bordered card, in stored chronological order (**oldest-first**), with auto-scroll to the bottom on open via a `ref` + `useEffect` **keyed on `issueId`** (not `source`, so a background poll never yanks the operator mid-read). `splitCommentEntries` and the `comment-entry` testid were removed; the `view-comments_md` container testid is retained, so `steer-flyout.spec.ts` / `flyout-tabs.spec.ts` `toContainText` assertions still hold. Verified: `tsc --noEmit` clean; `steer-flyout` specs pass [source: wiki/raw/sessions/2026-06-16-flyout-comment-ordering.md].

### e2e drift surfaced while verifying → resolved by decoupling the fixture (C-0221)

`tests/global-setup.mjs` mirrors the **live** `bindings.yml` into the e2e fixture; the `trading` binding was offboarded/purged (2026-06-15), so the fixture lost it and **16** specs broke — `seedIssue("trading", …)` hit `FOREIGN KEY constraint failed` (`issue.binding_name REFERENCES binding(name)`) for the mutating specs (`board-dnd`/`archive`/`dashboard`/`reply`), and the read-only specs (`board`/`run-detail`/`flyout-tabs`) timed out on the missing seed card. Confirmed pre-existing (identical on clean HEAD) — not the render change.

Migrating those specs onto `homelab` was rejected: the mutating specs use `trading` as a board **isolated** from the homelab specs that share the persistent dev DB under `fullyParallel` (dashboard roll-up counts, dnd/archive state assertions would collide). Fix (commit `b3e0f58`): `global-setup.mjs` synthesizes a stable fixture-only `trading` binding — deep-copy a local binding, force `type=coding`, drop any `remote:` block — so the e2e suite is decoupled from live-binding churn. `type=coding` matters: the flyout's 7-chip layout is the coding layout; infra bindings add 3 chips (`IssueFlyout.tsx:314`). No spec edits; full suite 47 passed (one unrelated `new-issue` combobox keyboard flake, green in isolation) [source: wiki/raw/sessions/2026-06-16-flyout-comment-ordering.md].

## Follow-on (2026-06-24) — patrol diagnostic blocks caused flyout horizontal overflow

Live homelab patrol comments introduced long fenced diagnostic dumps and compact JSON-ish patrol markers. The shared markdown renderer did not wrap `<pre>` blocks, so the flyout comments pane (`view-comments_md`) could become horizontally scrollable even though the outer dialog stayed within the viewport. A Playwright probe against a copy of live `podium.db` issue 66 measured `commentsOverflow: 4003` before the fix and `0` after it [source: web/frontend/components/Markdown.tsx] [source: web/frontend/tests/flyout-tabs.spec.ts].

Fix (`24d80f4`): `Markdown.tsx` now applies `break-words` plus `<pre>` `max-w-full`, `whitespace-pre-wrap`, and `break-words`, favoring wrapped diagnostic readability over preserving one very long line. `flyout-tabs.spec.ts` now seeds a patrol-style fenced JSON marker and asserts the comments pane has no horizontal overflow. Verification: touched-file LSP diagnostics clean, `pnpm exec tsc --noEmit`, `PYTHONPATH=../.. pnpm exec playwright test tests/flyout-tabs.spec.ts --project=chromium`, and a copy-of-live-DB probe all passed. Deployed with `web/frontend/deploy.sh` so `.next` was staged then swapped safely [source: web/frontend/deploy.sh].

## Follow-ups

- Frontend changes from the 2026-06-24 overflow fix are committed and deployed; earlier 2026-06-16 note below is historical.
- Frontend changes uncommitted at capture; Podium frontend needs `next build` + restart (or dev hot-reload) to show them; `npm run test:e2e` not yet run.
- ADR-0007 (`agent-summary-as-human-comment`) has no promoted wiki analysis page — candidate ingest opportunity.
- (2026-06-16) ~~The `trading`-bound e2e specs are broken by the trading offboarding~~ — **resolved** (commit `b3e0f58`): `global-setup.mjs` synthesizes a fixture-only `trading` binding; full suite green. See the e2e-drift section above and C-0221.
