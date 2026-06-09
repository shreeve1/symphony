# Session Capture: Trading Smoke Rate-Limit Debugging

- Date: 2026-06-09
- Purpose: Capture durable learnings from a live trading-binding smoke test that exposed post-agent Plane rate-limit and conversation-mode behavior.
- Scope: Symphony scheduler fixes, live smoke outcomes, verified commits/tests/service evidence, and follow-up risks. This is a curated summary, not a transcript.

## Durable Facts

- A trading smoke run for issue `6fbfd86a-36b2-4548-9b41-2a80fb66506c` exited cleanly but hit Plane 429 during post-agent reconciliation, leaving the issue in Running until later retained-worktree recovery. Evidence: journal query showed `agent_exited ... exit_code=0` followed by `HTTP/1.1 429 Too Many Requests`; fixes landed in `scheduler.py`; commits `a269e32`, `fbff782`, `c4944be`.
- Symphony now records post-agent Plane rate-limit interruptions in `_DispatchState.pending_review_issue_ids`, retries review reconciliation on later ticks, and can retain Running worktrees for review instead of waiting for claim timeout. Evidence: `scheduler.py#93-114`, `scheduler.py#919-930`, `scheduler.py#1495-1670`, `tests/test_scheduler.py#4315-4375`.
- Plane 429 cooldown now includes shared host-level `_PLANE_COOLDOWN_UNTIL` so one binding's 429 suppresses dispatch probes from other binding loops until the shared cooldown clears. Evidence: `scheduler.py#57`, `scheduler.py#117-173`, `tests/test_scheduler.py#3964-3990`.
- The optional `has-worktree` Role without a configured UUID no longer triggers a Plane label-resolution scan. This avoids large label pagination bursts when the optional label is absent. Evidence: `scheduler.py#832-839`, `tests/test_scheduler.py#529-557`.
- After `c4944be`, service restarted and reported `code_sha=c4944be`; startup reconcile retained old trading issue `6fbfd86a-36b2-4548-9b41-2a80fb66506c` for review with run id `ef2d127d`. Evidence: `journalctl -u symphony-host.service --since='1 minute ago'` after restart; commit log `c4944be fix: avoid optional label scans`.
- New trading smoke issue `0ab7f64c-3ad4-468d-8c2e-4d408c35f076` (sequence 6) dispatched, exited cleanly, and moved to In Review, but its run worktree was removed as clean and branch `symphony/run-e7f6c011` had no diff. Evidence: journal lines `run_worktree_created`, `agent_exited`, `state_transitioned ... state=in-review reason=agent-marker-review`, `worktree_removed run_id=e7f6c011`; `git worktree list`; `git branch --list symphony/run-e7f6c011 -v`.
- The dirty-worktree proof failed because unlabeled issues resolve/render as conversation mode, and conversation context explicitly instructs agents not to edit files. Evidence: `prompt_renderer.py#141-157`; session smoke outcome for issue `0ab7f64c-3ad4-468d-8c2e-4d408c35f076`.
- Verification after fixes: `python3 -m pytest` passed with 466 tests after the optional-label scan fix. Evidence: command output `466 passed in 4.32s`.

## Decisions

- James approved committing and restarting for three Symphony fixes: post-agent 429 review retry, shared Plane cooldown, and optional-label scan removal. Evidence: session approval prompts and commits `a269e32`, `fbff782`, `c4944be`.
- James approved one additional trading Plane smoke issue using the secret env file only for the single redacted Plane creation command. Evidence: session approval prompt and created issue `0ab7f64c-3ad4-468d-8c2e-4d408c35f076`.

## Evidence

- `scheduler.py` — post-agent rate-limit recovery, shared cooldown, optional label behavior.
- `tests/test_scheduler.py` — regression tests for post-agent recovery, shared cooldown, no optional-label scan, and retained worktree behavior.
- `prompt_renderer.py#141-157` — conversation-mode instructions forbid file edits.
- `~/trading/crypto-trading-agents/WORKFLOW.md` / `wiki/raw/workflow-trading.md` — trading safety policy and `Plans/<identifier>.md` plan path convention.
- `journalctl -u symphony-host.service` — live evidence for service `code_sha`, startup reconcile, issue dispatch, rate-limit, review transition, and worktree removal.
- `git log --oneline -5` — commits: `c4944be`, `fbff782`, `a269e32`, `5a12dcc`, `12c092a`.

## Exclusions

- No secrets, API keys, `.env` contents, token values, private keys, or raw environment dumps were captured.
- Full transcript was not captured.
- Raw Plane issue body text was summarized only; no sensitive trading configuration was stored.
- User approvals were summarized at decision level only.

## Open Questions And Follow-Ups

- Define a true execute mode, or route dirty-worktree landing proof through plan/build labels; unlabeled tickets are conversation mode and should not be used for file-change smoke tests.
- Decide whether trading `has-worktree` label should be created and assigned a UUID in `bindings.yml`, or remain absent so label behavior stays disabled.
- Consider reducing Plane request pressure further by limiting startup and tick pagination for nonessential sweeps.
- Current recovered smoke worktrees/branches include clean no-diff runs; cleaning stale branches/worktrees still requires explicit operator approval.
