# Session Capture: claude_runner idle-at-prompt stall — nudge-and-fail-fast fix

- Date: 2026-06-14
- Purpose: Run #23 hung ~43 min with no signal. Found a structural completion-detection gap in the Claude tmux adapter and landed a fix (option B: keep tmux, make the runner robust to non-compliance).
- Scope: Root cause of the idle hang, the fix in commit `9c058b7`, the rejected alternative (headless `claude -p`), live verification (reconcile of Run #23, Run #25 as a non-instance), and tunables. Excludes secret env values.

## Durable Facts

- **Symptom.** Run #23 (Podium issue 20 "remove binding", binding `symphony`, agent `claude`/`claude-opus-4-8`, cwd `/home/james/symphony`) dispatched 2026-06-14T19:55:01Z and sat `state=running` for ~43 min. The agent made one substantive edit (`remove_podium_binding()` in `skill_migration.py`) by 19:56:24Z, then went idle: process `S` (sleeping), zero outbound sockets (no API call in flight), transcript frozen — parked at the interactive prompt. — Evidence: `podium.db` run/issue rows, `ps`/`ss` on the tmux child, agent session transcript mtime
- **Root cause (structural).** The Claude adapter drives an interactive tmux REPL, which never exits, so there is no process-exit completion signal. `run_claude_agent` polled only two signals — `done_file.exists()` and `_session_alive()` false — every 1s until `run_timeout_ms` (default 3_600_000 ms = 1h). An agent that ends its turn without performing the completion protocol (write `result_file`, then touch `done_file`) is *alive* with *no done file*, indistinguishable from a working agent, so the loop waited out the full hour. Completion depended on the LLM remembering a 3-step closing ritual every run; models end turns early routinely, so this recurs. — Evidence: `claude_runner.py` poll loop (pre-fix lines 461-490), `_wrap_prompt`, `config.py:132` (`run_timeout_ms: int = 3_600_000`)
- **Fix (commit `9c058b7`).** Detect idle by watching the captured pane: while Claude works its spinner/elapsed-timer redraws the pane at least once per second, so a pane byte-for-byte unchanged across `IDLE_POLLS_BEFORE_NUDGE = 30` one-second polls means the agent is parked. On idle, paste a completion-protocol reminder into the live session (`_send_nudge` reuses `_paste_and_submit`) up to `IDLE_NUDGE_ATTEMPTS = 2` times; if still no done file, give up early returning the same shape as the hard timeout (`exit_code=-1`, `timed_out=True`) plus a distinct `claude_idle_no_completion` log line. — Evidence: `claude_runner.py` (poll loop + `_nudge_text`/`_send_nudge`, constants `IDLE_POLLS_BEFORE_NUDGE`/`IDLE_NUDGE_ATTEMPTS`), commit `9c058b7`
- **Implementation detail.** Idle is tracked with a consecutive-unchanged-pane counter, not wall-clock, so no `clock()` calls were added to the loop and the existing timing-sensitive tests are unaffected. Done-file and session-dead branches are unchanged and still checked first each iteration. — Evidence: `claude_runner.py`, `tests/test_claude_runner.py`
- **Downstream mapping unchanged.** `timed_out=True` (and `exit_code != 0`) both map to `state=failed`, `verdict=blocked`, issue block + operator notify in `scheduler.py:1656`, so idle-exhaustion reuses the battle-tested terminal-timeout path, just reached faster. — Evidence: `scheduler.py:1656-1714`
- **Tests.** Three added to `tests/test_claude_runner.py`: idle→nudged once→completes (exit 0); idle→nudges exhausted→exit -1/`timed_out` with `completion nudges` stderr + kill-session; changing pane→never nudged across >30 polls (guards against false-nudging a working agent). Full suite `uv run pytest -q` → 789 passed, 2 skipped. — Evidence: `tests/test_claude_runner.py`, suite run this session
- **Run #25 was NOT an instance.** Issue 19 "File editing" (resumed claude session) was a legitimately long coding turn — `R` running, ~18% CPU, live API connection, transcript writing in real time — and later completed normally (`succeeded`/`review`, ended 20:34:24Z). Confirms the protocol works when the model complies. — Evidence: `ps`/`ss` during the run, `podium.db` run 25 row
- **Live verification.** Restarted `symphony-host.service` onto `9c058b7` (`symphony_started code_sha=9c058b7 bindings=3`, new MainPID 219195). Startup reconcile (`run_reconcile binding=symphony reaped=1`, `reconcile_startup_completed cleaned=1`) finalized orphaned Run #23 → `failed`/`blocked` (ended 20:38:21Z); issue 20 → `blocked`. Old Run #23 tmux was killed by systemd cgroup stop (socket reaper `count=0` — nothing left to reap). Dispatch loop live, no errors. — Evidence: `journalctl -u symphony-host.service` boot window, `podium.db` post-reconcile rows

## Decisions

- **Option B over option A.** Rejected switching the Claude path to headless `claude -p` (which would give a process-exit completion signal and delete the whole sentinel protocol). Operator constraint: "We can't go to claude -p." Chose option B — keep the tmux REPL, make the runner robust to turn-end non-compliance via idle detection + nudge + fail-fast. — Evidence: operator instruction this session
- **Reuse the hard-timeout result shape for idle-exhaustion** rather than a new exit code, to land on the existing failed/blocked terminal path with no scheduler changes; distinguish via stderr text and the `claude_idle_no_completion` log. — Evidence: `claude_runner.py`, `scheduler.py:1656`
- **Tunables:** `IDLE_POLLS_BEFORE_NUDGE = 30` (~30s idle window) and `IDLE_NUDGE_ATTEMPTS = 2`. Idle-exhaustion fails in ~90s instead of the prior ~1h. — Evidence: `claude_runner.py`

## Evidence

- `claude_runner.py` — idle-counter poll loop, `_nudge_text`, `_send_nudge`, constants; commit `9c058b7`
- `tests/test_claude_runner.py` — three new idle tests + fakes
- `scheduler.py:1656-1714` — `timed_out`/`exit_code` → failed/blocked verdict mapping
- `config.py:132` — `run_timeout_ms` default 1h
- `podium.db` — Run #23/#25 and issue 19/20 rows before and after reconcile

## Exclusions

- No `/home/james/symphony-host.env` values read or stored.
- Run #23's uncommitted `skill_migration.py` work product left in the working tree (orphaned run's output); not committed with the fix.

## Open Questions And Follow-Ups

- Pane-stability idle detection assumes the Claude TUI redraws (spinner/elapsed timer) at least once per second while working. If a future Claude Code TUI version stops animating during long quiet tool calls, the 30-poll window could false-positive; the changing-pane test guards the common case but the assumption is version-coupled.
- A nudge submits a fresh turn into the live session; if the agent had genuinely parked via the `SYMPHONY_QUESTION` protocol but failed to write the done file, the nudge would prod it — acceptable, since a parked question still requires the done file to surface.
