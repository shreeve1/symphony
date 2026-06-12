---
name: symphony-restart
description: Restart symphony-host.service with a pre-sanity → restart → verify-log-lines ritual. Use when bringing the Symphony scheduler onto new code, recovering from a stale process, or after editing scheduler config. Read-only sanity gate runs first; sudo restart only after James approves at the moment of action.
---

# Symphony Restart

Restart the host-native Symphony scheduler safely. This skill controls only `symphony-host.service`; Podium API/web deploys use their own service runbook.

## Prerequisites

- Symphony repo at `/home/james/symphony`.
- Service unit `symphony-host.service` exists.
- Journal reads are available.
- `sudo systemctl restart symphony-host.service` requires James's fresh approval in the current turn.

## Safety rules

- Never restart, stop, start, reload, or edit units without explicit James approval.
- Never read or print `/home/james/symphony-host.env`.
- Never mutate Podium, Plane, `bindings.yml`, issues, runs, or worktrees from this skill.
- If sanity fails, stop and report evidence; do not repair inside this skill.
- If disk head and running `symphony_started code_sha` already match, say no restart is needed and ask whether James still wants one.

## Workflow

### 1. Pre-restart sanity

Run from `/home/james/symphony`:

```bash
cd /home/james/symphony

git log --oneline -1
git status --porcelain
systemctl show symphony-host.service \
  --property=ActiveState,SubState,MainPID,ActiveEnterTimestamp,WorkingDirectory --no-pager
journalctl -u symphony-host.service --since="5 minutes ago" -n 80 --no-pager \
  | grep -E 'ERROR|Traceback|ConfigError|reconcile_startup_failed|run_reconcile_failed' \
  || echo "no recent matched errors"
journalctl -u symphony-host.service --since="2 hours ago" --no-pager \
  | grep 'symphony_started' | tail -1
```

Capture:

- disk head SHA and subject.
- working-tree state.
- service active/substate/PID/start time.
- latest running `code_sha` from `symphony_started`.
- recent matched error count.

Optional tests if James asks for `--with-tests`:

```bash
uv run pytest -q
```

### 2. Sanity verdict

Report:

```text
disk head      <sha> <subject>
running sha    <sha from latest symphony_started> (matches | stale | unknown)
working tree   clean | dirty: <paths>
service state  active/running | <state>/<substate>
recent errors  none | <count> matched lines
tests          not run | passed | failed
```

Stop if service is unhealthy, recent errors are unexplained, or the tree has risky unrelated changes. Ask James before proceeding if the only issue is an expected dirty tree.

### 3. Approval gate

Show exact command and reason:

```text
About to run:
  sudo systemctl restart symphony-host.service

Reason: <stale code sha | config reload | manual operator request>
Proceed? (y/n)
```

Do not proceed without explicit approval.

### 4. Restart

```bash
sudo systemctl restart symphony-host.service
sleep 5
systemctl show symphony-host.service \
  --property=ActiveState,SubState,MainPID,ActiveEnterTimestamp --no-pager
```

If not active/running, capture last 80 lines and stop:

```bash
journalctl -u symphony-host.service --since="1 minute ago" -n 80 --no-pager
```

### 5. Verify scheduler lifecycle

Wait for the first dispatch/reconcile cycle:

```bash
sleep 35
journalctl -u symphony-host.service --since="1 minute ago" --no-pager -n 250 \
  | grep -E 'symphony_started|reconcile_startup_(begin|done|failed)|run_reconcile_(begin|done|failed)|dispatch_completed|ERROR|Traceback'
```

Expected evidence:

- one `symphony_started service=symphony code_sha=<sha> bindings=<N>` line.
- one `reconcile_startup_begin` and matching `reconcile_startup_done` per binding.
- `run_reconcile_begin` / `run_reconcile_done` for Podium bindings when run reconciliation is enabled.
- at least one `dispatch_completed` line showing the scheduler loop is alive.
- zero `ERROR` / `Traceback` / `reconcile_startup_failed` lines since restart.

### 6. Verdict

Report:

```text
restart        ok | failed  pid=<n> started=<iso>
code_sha       <sha from symphony_started>
bindings       <N>: <names if visible>
reconciles     <begin>/<done>/<failed>
run_reconcile  <begin>/<done>/<failed | n/a>
dispatch_loop  alive (last: dispatched=<bool> reason=<reason>)
errors         <count> since restart
```

If verification fails, report exact failing log line and recommend next skill: `symphony-troubleshooter` for diagnosis or another targeted skill after James chooses.

## Verification

Run:

```bash
cd /home/james/symphony && uv run pytest tests/skills/test_restart_troubleshooter.py
```
