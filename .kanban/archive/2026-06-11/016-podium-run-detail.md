---
id: 016
title: Podium — Run detail + history view
status: done
blocked_by: [012c]
parent: null
priority: 0
created: 2026-06-10
updated: 2026-06-11
actor: ralph
---

## What to build

Operator can drill from a Run row in the issue flyout into a full Run detail
panel: verdict, summary, cost, tokens, branch, started/ended timestamps,
skill invoked, and a link to the on-disk log file at `runs/{id}.log`.

Endpoint:

- `GET /api/runs/{id}` → full run row.
- `GET /api/runs/{id}/log` → tail of `runs/{id}.log` (last 1MB; sets
  `Content-Type: text/plain`). Returns 404 if the file does not exist.

Frontend:

- Run rows in the issue flyout (S012) become clickable.
- Run detail opens in a stacked sub-flyout (slides over the issue flyout,
  closable back to the issue).
- Top: metadata grid (agent, provider, model, verdict, summary, cost,
  tokens, started, ended, duration, branch).
- Bottom: log viewer pane — `<pre>` tag rendering the response of
  `/api/runs/{id}/log`, monospace, scroll-locked to bottom on load. "Reload"
  button refetches.
- Empty log: "No log on disk for this run."

Cost field in the metadata grid stores raw `cost_usd` from the DB but is
hidden in the UI (per the grilling decision to drop cost visualization).
Implementation: don't render the `cost_usd` cell; ship the column unused.

## Acceptance criteria

- [x] `GET /api/runs/{id}` returns the full row with all schema columns.
- [x] `GET /api/runs/{id}/log` returns the file contents when the log exists; 404 with `{"detail": "log_not_found"}` when it doesn't.
- [x] Log response is capped at 1MB (test creates a 2MB log, asserts response body length ≤ 1_048_576 and that the *tail* is returned).
- [x] Playwright `run-detail.spec.ts`: open issue flyout → click first run row → metadata grid renders → log pane renders → "Reload" refetches.
- [x] Run detail does not render `cost_usd` (assert `data-testid="run-cost"` absent).
- [x] `web/api/tests/test_run_endpoints.py` covers both endpoints.

## Verification

```
cd /home/james/symphony && uv run pytest && \
cd web/frontend && pnpm test:e2e
```

## Blocked by

- #012

## Implementation Notes

- Added `GET /api/runs/{id}` and `GET /api/runs/{id}/log` endpoints.
- Added 1MB tail-log behavior and endpoint regression tests.
- Added clickable run rows, stacked run detail flyout, metadata grid, log pane, and reload action.
- Verified with `uv run pytest`, `pnpm test:e2e`, and `pnpm exec tsc --noEmit`.
