---
id: 104
title: MANUAL — live calibration against disposable n8n checkout, ADR flip, wiki
status: pending
blocked_by: [103]
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

- [ ] One attended live dispatch completes with a captured result + `done.0`.
- [ ] Remote tmux server, socket, and temp dir are verified gone after the run.
- [ ] `ssh <remote> tmux -V` recorded ≥ 3.2; TUI timing constants recorded (and adjusted
      if needed).
- [ ] ADR-0012 v2 amendment flipped to `accepted` with calibration findings.
- [ ] `/wiki-update` pass done.

## Verification

Attended / manual — no automated command. Evidence: the captured `result.0.txt`, the
post-run remote-residue check, and the ADR-0012 status diff.

## Blocked by

- Blocked by #103
