---
id: 009
title: claude Agent Adapter (tmux send-keys)
status: done
blocked_by: [3]
updated: 2026-06-05
actor: ralph
parent: null
priority: 0
created: 2026-06-04
---

## What to build

Add the **claude** Agent Adapter implementation behind the #003 interface,
porting the proven `dev-review-claude` engine: a private-socket tmux session,
`new-session`, prompt delivery via `load-buffer`/`paste-buffer` + `Enter`, poll
`capture-pane` for a per-run nonce **Done Marker**, `kill-session`, then diff the
working tree. Scrape `SYMPHONY_RESULT` / `SYMPHONY_SUMMARY` from the pane before
the Done Marker (ANSI handling per current rules), backstopped by post-run
side-effect inspection (commit present for build, plan artifact written for
plan). `agent:claude` / `default_agent: claude` routes a Run here; the tmux
session name comes from the deterministic run-id scheme (#004).

See `docs/adr/0001-claude-via-tmux-send-keys.md`.

## Acceptance criteria

- [x] A `ClaudeAgentAdapter` drives the full tmux lifecycle (session create → paste → poll → kill) against a mocked tmux.
- [x] The per-run Done Marker nonce is detected to signal completion (no exit code relied on).
- [x] `SYMPHONY_RESULT`/`SYMPHONY_SUMMARY` are scraped from the pane; absent/unknown falls through to the side-effect backstop.
- [x] A binding/issue selecting claude dispatches via this adapter; pi path unaffected.
- [x] tmux session name follows the #004 run-id naming scheme.
- [x] Suite green with mocked-tmux coverage.

## Verification

`uv run pytest`

## Blocked by

- Blocked by #3

## Implementation Notes

Added `ClaudeAgentAdapter` using a private per-run tmux socket/session, `load-buffer`/`paste-buffer` prompt delivery, polling for a nonce done marker, pane scraping before the marker, and cleanup via `kill-session`. Added `RoutingAgentAdapter` so `default_agent: claude` and `agent:claude` labels dispatch through the Claude adapter while the pi path remains unchanged. Verified with `uv run pytest`, critical LSP diagnostics for touched files, and mandatory fresh review (`RALPH_REVIEW: PASS_WITH_NOTES`).
