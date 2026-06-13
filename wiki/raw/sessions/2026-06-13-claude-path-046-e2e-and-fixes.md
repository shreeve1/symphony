# Session Capture: Claude dispatch path — first live #046 E2E, two tmux races found + fixed

- Date: 2026-06-13
- Purpose: First-ever live end-to-end test of the Claude (tmux) dispatch path, to verify the #046 output contract there (the Pi path was confirmed in C-0166; the Claude path / C-0154 was unit-test-only). Surfaced two reliability bugs in the tmux send-keys flow and fixed them.
- Scope: Two live Claude-routed homelab smoke Issues (id 6, 7), manual tmux reproductions, root-cause, and a code fix in `claude_runner.py` with tests. Made-live/restart is a separate follow-up.

## Durable Facts

- **The #046 contract design works on Claude.** A manual reproduction of the exact adapter flow (tmux `new-session claude --permission-mode bypassPermissions --model claude-opus-4-8`, paste the wrapped prompt, poll done/result) produced a correct result file: a verbatim `SYMPHONY_SUMMARY_BEGIN/END` block + `SYMPHONY_RESULT: done`, written result-first then done. — Evidence: manual repro in `/home/james/homelab`, result file 1839 bytes.
- **Run-row fields are correct on the Claude path (C-0152 confirmed live):** the `run` rows for issues 6/7 stored `agent=claude`, `provider=''` (empty), `model='claude-opus-4-8'` (bare, no `:effort` suffix). — Evidence: `sqlite3 podium.db "SELECT agent,provider,model FROM run WHERE issue_id IN (6,7)"`.
- **Bug 1 — paste/Enter race (root cause).** `claude_runner.run_claude_agent` did `paste-buffer` then `send-keys Enter` with no settle delay. For the full ~217-line rendered prompt the Enter is absorbed into the paste and the prompt is never submitted — the live tmux pane (via `nsenter`, because `PrivateTmp=yes`) showed `❯ [Pasted text #1 +217 lines]` unsubmitted. The run then idles until the 60-min timeout. Issue 7 reproduced this; a single manual Enter submitted it and claude ran normally. — Evidence: live pane capture of issue 7; journal showing 8+ min `running` with no progress.
- **Bug 1 variant / Bug 2 — done-before-result race.** When the paste partially submits (issue 6) or in general, claude touches the done file a beat before the result write is visible; the adapter treated "done exists, result empty" as an instant hard `137` with **no grace re-poll and no pane capture** (the only failure branch that didn't capture the pane). Issue 6 failed this way in 17.6s; issue 7 failed the same way after I unstuck it. — Evidence: issue 6/7 comments "claude done file exists but result file is missing or empty"; `claude_runner.py:267-276` (pre-fix).
- **A 1-second settle delay before Enter made the manual repro reliable** (done at ~10s, result complete at the instant done appeared). This is the basis of the fix. — Evidence: tight manual repro, result bytes at done == bytes at +2s (no fill-in needed once submit was clean).
- **`symphony-host.service` has `PrivateTmp=yes`**, so per-run Claude tmux sockets live in the service's private `/tmp` (invisible to other shells; observe via `nsenter -t <MainPID> -m`). The #044 orphan-socket reaper's `/tmp/symphony-claude-*.sock` glob therefore operates within that private namespace, which a fresh service start wipes anyway. — Evidence: `systemctl show symphony-host.service --property=PrivateTmp`; `nsenter` socket listing.

## Decisions

- James approved filing Claude smoke Issues for this verification and chose to implement "both fixes + tests" with a wiki capture. — Evidence: this session.

## The fix (claude_runner.py, working tree — not yet live)

- New `_paste_and_submit`: after `paste-buffer`, sleep `PASTE_SETTLE_SECONDS=1.0`, then send Enter and re-send (up to `SUBMIT_RETRY_ATTEMPTS=3`, `SUBMIT_RETRY_INTERVAL_SECONDS=1.0`) while the pane still shows a `[Pasted text …]` placeholder (`_paste_pending`).
- New `_read_result_with_grace`: on done, re-poll the result file for up to `RESULT_GRACE_SECONDS=3.0` (step `0.5`, iteration-bounded so it terminates under a frozen test clock) before declaring it empty.
- The done-but-empty `137` branch now captures the pane tail into stderr for diagnosis (was previously lost).
- Tests added: submit-retry, grace-fill-success, done-empty-captures-pane. `uv run pytest` 716 passed, 1 skipped; ruff clean.

## Evidence

- `claude_runner.py`, `tests/test_claude_runner.py` — the fix + tests.
- Issues 6 (blocked, claude minimal-prompt path), 7 (blocked, after manual unstick) left in Podium as audit evidence.
- `/tmp/handoff-claude-046-contract.md` — the Claude verification handoff this session executed.

## Exclusions

- No secrets read (`symphony-host.env` untouched; `_claude_env` allowlist confirmed to exclude `ANTHROPIC_API_KEY` — Claude auth comes from the service user's HOME claude login).
- Manual reproductions ran read-only in `/home/james/homelab`; no changes/commits made there.

## Open Questions And Follow-Ups

- **C-0154 still not confirmed on a successful *scheduler* Claude run** — both live runs failed before completion. Needs a re-test after the fix is restarted live.
- Make the fix live: `symphony-host` restart required (claude_runner is in-process). Then re-file a Claude smoke and confirm the #046 completion comment end-to-end.
- Consider a fast-fail/warn when a prompt looks pasted-but-unsubmitted, so a stuck run doesn't burn the full 60-min timeout.
