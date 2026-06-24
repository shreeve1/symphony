---
id: 104
title: MANUAL — live calibration against disposable n8n checkout, ADR flip, wiki
status: done
blocked_by: [103]
updated: 2026-06-23
parent: 96
priority: 0
created: 2026-06-23
---

## What to build

**MANUAL / attended — Ralph cannot build this.** It launches
`--permission-mode bypassPermissions` Claude on a real remote host over SSH and requires
live TUI calibration; there is no automated verification. Execute by hand once #99–#103
are merged. Source of truth: `plans/feature-remote-claude-dispatch.md` (Groups 6 + 7).

1. Stand up a **disposable** checkout on n8n (NOT `/home/itadmin/itastack`) and a
   temporary local coding+claude remote binding pointing at it. Operator-attended.
2. Before dispatch, confirm remote tmux is capable: `ssh <remote> tmux -V` ≥ 3.2 (the
   remote tmux is what actually executes the `new-session -c/-e` flags).
3. Dispatch one issue through the real `run_claude_agent` path and confirm: remote launch
   in the right cwd, readiness incl. consent modal, paste/submit, done-file over SSH,
   result captured, and remote teardown (tmux server gone, remote socket + temp dir
   removed, ControlMaster closed).
4. Calibrate the TUI constants if SSH latency shifts them (`PASTE_SETTLE_SECONDS`,
   `READY_TIMEOUT_SECONDS`, paste/Enter retry, `RESULT_GRACE_SECONDS`); record measured
   ready/done timings regardless.
5. Tear down the disposable checkout and the temporary binding.
6. Flip the ADR-0012 v2 amendment status `proposed` → `accepted`; append calibration
   findings to its progress log.
7. Run the `/wiki-update` pass (analyses row for adr-0012, ROUTING.md keywords,
   `wiki/log.md`, `wiki/CLAIMS.md`).

## Acceptance criteria

- [x] One attended live dispatch completes with a captured result + `done.0`.
- [x] Remote tmux server, socket, and temp dir are verified gone after the run.
- [x] `ssh <remote> tmux -V` recorded ≥ 3.2; TUI timing constants recorded (and adjusted
      if needed).
- [x] ADR-0012 v2 amendment flipped to `accepted` with calibration findings.
- [x] `/wiki-update` pass done.

## Verification

Attended / manual — no automated command. Evidence: the captured `result.0.txt`, the
post-run remote-residue check, and the ADR-0012 status diff.

## Blocked by

- Blocked by #103

## Implementation Notes

- Created disposable n8n checkout at `/tmp/symphony-calibration`; verified `ssh itadmin@100.95.224.218 tmux -V` = `tmux 3.4`.
- Added temporary `calibration-claude` remote binding and restarted `symphony-host`; startup logged `bindings=6` and `remote_repo_reachable binding=calibration-claude sha=7e4a319`.
- Created Podium smoke Issues #115/#116; Runs #324/#325 dispatched through the production scheduler to `ClaudeAgentAdapter`/`SshClaudeHost`, exited 0, captured non-empty `result.0.txt` plus `done.0`, reported cwd `/tmp/symphony-calibration`, and recorded remote HEAD `7e4a319`.
- Observer trace for Run #325: first ready/prompt sample ~4.8s after dispatch, command output ~9.6s, `result.0.txt` ~13.0s, `done.0` ~19.6s, runner exit 20.9s. No timing constants changed.
- Verified issue-specific remote temp dirs/sockets removed, SSH ControlMaster closed, and disposable checkout clean; scope was read-only smoke, not edit/commit landing.
- Created follow-up #105 to keep remote Claude edit+commit landing verification visible.
- Flipped ADR-0012 v2 amendment to accepted and updated wiki analysis/index/CLAIMS/log (C-0313).
- Teardown: temporary binding/Podium rows and remote disposable checkout removed; scheduler restarted back to normal 5-binding config.
