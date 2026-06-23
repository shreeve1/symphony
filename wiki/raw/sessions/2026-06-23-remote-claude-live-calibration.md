# 2026-06-23 Remote Claude live calibration

Curated evidence for Issue #104 / ADR-0012 v2 acceptance. No secrets included.

## Environment

- Remote host: `itadmin@100.95.224.218` (`n8n`)
- Remote tmux: `tmux 3.4`
- Disposable checkout: `/tmp/symphony-calibration`
- Temporary binding: `calibration-claude`
- Scheduler restart for calibration logged `symphony_started service=symphony code_sha=f273b66 bindings=6`
- Remote reachability logged `remote_repo_reachable binding=calibration-claude host=100.95.224.218 sha=7e4a319`

## Production smoke runs

Podium smoke Issues #115/#116 were inserted for the temporary binding and dispatched by the live scheduler.

| Issue | Run | Result | Remote cwd | Remote SHA | Duration |
|---|---:|---|---|---|---:|
| 115 | 324 | `SYMPHONY_RESULT: done` / exit 0 | `/tmp/symphony-calibration` | `7e4a319` | 22.5s |
| 116 | 325 | `SYMPHONY_RESULT: done` / exit 0 | `/tmp/symphony-calibration` | `7e4a319` | 20.9s |

Run logs: `runs/324.log`, `runs/325.log`.

## Observer timing samples for Run #325

`claude_dispatch` log: `2026-06-23 23:43:26,366`, cwd `/tmp/symphony-calibration`, `resumed=false`.

Samples from 1s observer loop using remote `tmux capture-pane` and temp-dir listing:

- `23:43:31.171` — first captured ready/prompt state; socket `/tmp/symphony-claude-116-76e631bf573f.sock`; remote temp dir contained `prompt.txt`. Approx dispatch→ready sample: 4.8s.
- `23:43:34.453` — Claude had submitted/started `Bash(pwd && git rev-parse --short HEAD)`. Approx dispatch→command start sample: 8.1s.
- `23:43:36.115` — command output visible: `/tmp/symphony-calibration`, `7e4a319`. Approx dispatch→command output sample: 9.7s.
- `23:43:39.400` — remote temp dir contained `result.0.txt`. Approx dispatch→result-file sample: 13.0s.
- `23:43:45.971` — remote temp dir contained `done.0`, `prompt.txt`, `result.0.txt`. Approx dispatch→done-file sample: 19.6s.
- `23:43:46.670` — runner logged `agent_exited issue_id=116 exit_code=0 duration_ms=20915 timed_out=false`.

No `claude_ready_timeout`, `claude_modal_stuck`, `claude_idle_nudge`, `claude_permission_modal_approved`, or `claude_question_modal_autoreplied` lines appeared for these production runs. Existing constants held: `READY_TIMEOUT_SECONDS=30.0`, `PASTE_SETTLE_SECONDS=1.0`, `SUBMIT_RETRY_INTERVAL_SECONDS=1.0`, `RESULT_GRACE_SECONDS=3.0`.

## Cleanup evidence

After Run #325 and after teardown:

- `ls -ld /tmp/symphony-claude-115-* /tmp/symphony-claude-116-*` on n8n returned no matches.
- Local ControlMaster socket `/tmp/symphony-claude-100.95.224.218.ctl` was gone after ControlPersist elapsed.
- Disposable checkout `git status --short` was clean before deletion.
- `/tmp/symphony-calibration` was removed.
- Temporary Podium rows for Issues #115/#116, Runs #324/#325, and binding `calibration-claude` were deleted.
- `bindings.yml` restored to five bindings and scheduler restarted; post-teardown startup logged `symphony_started ... bindings=5`, reconciled all five bindings, and reported no matched errors.

## Scope note

The calibration was intentionally read-only. It proved the production scheduler/routing/runner path, result/done capture, timing envelope, and cleanup. It did not exercise a remote edit/commit landing flow.
