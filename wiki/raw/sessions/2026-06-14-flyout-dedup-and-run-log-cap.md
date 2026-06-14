# Session Capture: Issue fly-out dedup (context tab + run summary) and run-log size decouple

- Date: 2026-06-14
- Purpose: Resolve operator-reported duplication in the Podium issue fly-out (comments tab ≈ context tab; a third copy in the run-detail summary row) and decouple the on-disk run-log size cap from the comment/context bound so the run-detail pane can show full output.
- Scope: Frontend fly-out changes (uncommitted), one scheduler.py change (committed `e0c02b4`, restarted live), the verified root-cause mechanism, and the resulting documentation deltas.

## Durable Facts

- **Why comments/context/run-summary looked identical.** For a `pi_mode: rpc` binding (all three live bindings: homelab, trading, symphony), `run_pi_rpc_agent` returns `"".join(assistant_parts)` as stdout, where `assistant_parts` is built only from `text_delta` assistant events — thinking deltas and tool-call deltas are excluded (`_assistant_delta`). So stdout = the agent's spoken prose = the `SYMPHONY_SUMMARY_BEGIN…END` block. Symphony then fans that one block into three stores: extracted → `comments_md` (the human thread), full stdout → `context_md` (the AI continuity log), and the parsed summary → `run.summary`. A terse agent (e.g. the `prime` skill) emits only the summary block, so all three coincide; a chatty agent that narrates between tool calls makes `context_md` richer than `comments_md`. — Evidence: `agent_runner.py:888` (`_assistant_delta`), `agent_runner.py:567` (RPC stdout join), `scheduler.py` `_extract_summary`/`append_context` fan-out, live `podium.db` issue 12 ("Prime", binding trading): `comments_md` 3866 chars vs `context_md` 3942 chars, same summary text wrapped differently.
- **`context_md` is load-bearing, not redundant.** It is the Continuity re-feed floor (injected into fresh/fallback dispatches) and the compaction substrate (#026); ADR-0007 explicitly leaves it and its `### Symphony Context Append` wrapper unchanged. Under RPC + Session Resume it is *not* injected on the resume path (the native session is authoritative) — only the fallback floor. So its UI read is "incidental observability." The fix was therefore display-only; the store/write path was untouched. — Evidence: `CONTEXT.md` Issue Context glossary, `docs/adr/0007-agent-summary-as-human-comment.md`, `scheduler.py` `_maybe_compact_context`.
- **Fly-out changes (display-only).** `IssueFlyout.tsx`: `TABS` dropped `"context"` → `["comments","session"]`; removed the context render branch and the now-orphaned `MarkdownEditor` (its only consumer was `context_md`). `RunDetailPanel.tsx`: removed the `["summary", …]` row from the run-metadata grid. The `context_md` API field/type and seed columns remain (backend still serves/accepts it). Operators now inspect per-run output via the **Run Log pane**, not a context tab. — Evidence: `web/frontend/components/IssueFlyout.tsx`, `web/frontend/components/RunDetailPanel.tsx`, `web/frontend/tests/flyout-tabs.spec.ts`, `web/frontend/tests/editing.spec.ts` (context-edit test removed — `context_md` was the only operator-editable markdown field; editing capability intentionally lost, consistent with the glossary "does not normally write").
- **Run-log size cap decoupled from comment/context bound.** Previously `_format_report` ran `_sanitize_report` (ANSI-strip + secret-redact + tail-truncate to `REPORT_MAX_BYTES = 2048`) and the same 2 KB result fed *both* `_write_run_log` (the run-log pane) and `append_context` (`context_md`). So the run-log pane only ever showed the last 2 KB tail. Change: added `LOG_MAX_BYTES = 1_048_576`; `_sanitize_report(text, secrets, *, max_bytes=REPORT_MAX_BYTES)` now takes a cap; `_finish_run_record` drops its `stdout`/`stderr` params, takes `secrets`, and builds the log from the raw `result.stdout`/`result.stderr` sanitized at `LOG_MAX_BYTES`. Comment + `context_md` paths stay at 2 KB (compaction token budget untouched). Secret-redaction + ANSI-strip still apply to the log. — Evidence: `scheduler.py` commit `e0c02b4`, `REPORT_MAX_BYTES`/`LOG_MAX_BYTES` constants, `_sanitize_report`, `_finish_run_record`, 11 call sites now passing `secrets=secrets`.
- **Existing run logs already lost their pre-2 KB content** (truncation happened at write time, not display). Only runs after the `e0c02b4` restart get the ~1 MiB tail.

## Decisions

- Drop the context tab rather than relabel it — James: "drop context since I can use the run log pane." — Evidence: this session.
- Run-log cap = 1 MiB bounded (not unbounded) to protect the run-log dir from a pathological multi-GB stdout. — Evidence: this session.
- Commit `scheduler.py` before restart so `symphony_started code_sha` honestly reflects the running code; frontend left uncommitted (separate Next-app concern). — Evidence: this session, commit `e0c02b4`.

## Evidence

- `scheduler.py` (commit `e0c02b4`) — `LOG_MAX_BYTES`, parameterized `_sanitize_report`, `_finish_run_record` signature change.
- `web/frontend/components/IssueFlyout.tsx`, `RunDetailPanel.tsx` — fly-out dedup (uncommitted at capture time).
- `agent_runner.py:888,567` — RPC stdout is assistant `text_delta` prose only.
- Live verification: `uv run pytest` 776 passed / 2 skipped; restart to `code_sha=e0c02b4`, `reconcile_startup_*` + `dispatch_completed` + `pi_rpc_probe_ok` clean.

## Exclusions

- No secrets or `/home/james/symphony-host.env` contents captured.
- Did not capture the full issue-12 `comments_md`/`context_md` dump (operational data); only lengths and the structural observation.

## Open Questions And Follow-Ups

- Frontend changes (`IssueFlyout.tsx`, `RunDetailPanel.tsx`, two specs) remain uncommitted and the Podium frontend needs a `next build` + restart (or dev hot-reload) to show them; e2e suite (`npm run test:e2e`) not yet run (needs live server + seeded DB).
- ADR-0007 is referenced here but has no promoted wiki analysis page (the `agent-summary-as-human-comment` decision). Candidate ingest opportunity.
