# 06 — F3: Live-tail consumer + catch-up flow

**What to build:** the chat flyout subscribes to `run.tail`, snapshots via `GET /api/runs/{id}/tail` on open/reconnect, and renders JSONL deltas with tool pills, auto-clustering, activity-status row, and lockstep/typewriter streaming. On `source_id` change → reset + refetch. Completed runs render from the durable record only (no transcript browse).

**Blocked by:** #32 (B3 — `run.tail` protocol and `/tail` endpoint must exist server-side first).

**Status:** ready-for-agent

- [ ] New consumer of `run.tail` filtered by `(issue_id, run_id)` (drop buffered lines whose `line_cursors[i] ≤ snapshot.cursor`, append the rest)
- [ ] Catch-up flow on flyout-open + reconnect: subscribe → snapshot via `GET /api/runs/{active_run_id}/tail` → render → dedupe
- [ ] Pin the local-pi session-JSONL event vocabulary (the one un-pinned piece of the spec — confirm or implement the mapping to §6's tool-pill/delta anatomy)
- [ ] Per-pill row cap (200 lines × 200 chars) with "show more"; tool-pill icons per the extensibility map (Bash→$, Read→R, Write→W, Edit→E, Glob→G, Grep→?, Task→T, TodoWrite→✓)
- [ ] 3+ consecutive tool pills auto-cluster into one header; threshold server-driven (UI knob, not hardcoded)
- [ ] Activity-status row above the chat: `thinking` (cyan pulse) / `tool_executing` (purple spin); `aria-live="polite"`
- [ ] `marked.parse()` → `DOMPurify.sanitize()` → Prism pipeline; SRI hashes preserved on CDN deps; one `pi-lens-ignore` comment per `innerHTML`-set call
- [ ] Typewriter streaming GATED behind `prefers-reduced-motion: reduce`
- [ ] On `source_id` change → reset + refetch (rotation observable)
- [ ] Completed runs: only the terminal bubble + summary + `comments_md` natural turn — no chat affordance for transcript browse (per i-a)
- [ ] Web Notification fires on turn finish only when `document.hidden`

Verification: `uv run pytest web/frontend/tests/session-tail.spec.ts -q` (via Playwright)

Provenance: spec §5, §6, §13.5; §6's "scope-cut order if needed" prioritized: plan-confirmation widget, tool-pill auto-clustering, file @mentions, toast container.

Wiki refs: [concepts/session-resume-continuity.md].
