---
name: symphony-restart
description: Restart symphony-host.service with a pre-sanity → restart → verify-log-lines ritual. Use when bringing the Symphony scheduler onto new code, recovering from a stale process, or after editing scheduler config. Read-only sanity gate runs first; sudo restart only after James approves at the moment of action.
---

# Symphony Restart

Restart the host-native Symphony scheduler safely. This skill controls only `symphony-host.service`; Podium API/web deploys use their own service runbook.

## Prerequisites

- Symphony repo at `/home/james/symphony`.
- Service unit `symphony-host.service` exists.
- Journal reads are available. **On this host the invoking user is not in `adm`/`systemd-journal`, so plain `journalctl -u symphony-host.service` silently returns no service lines** (it prints a "you are not seeing messages from other users" hint and an empty result — running `code_sha` comes back unknown). Use **`sudo journalctl ... -q`** for every journal read in this skill; the `-q` suppresses the hint. If `sudo` is unavailable, report running-sha as `unknown (journal not readable)` rather than treating empty output as "no errors".
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
sudo journalctl -u symphony-host.service --since="5 minutes ago" -n 80 --no-pager -q \
  | grep -E 'ERROR|Traceback|ConfigError|reconcile_startup_failed|run_reconcile_failed' \
  || echo "no recent matched errors"
sudo journalctl -u symphony-host.service --since="2 hours ago" --no-pager -q \
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
sudo journalctl -u symphony-host.service --since="1 minute ago" -n 80 --no-pager -q
```

### 5. Verify scheduler lifecycle

Wait for the first dispatch/reconcile cycle:

```bash
sleep 35
sudo journalctl -u symphony-host.service --since="1 minute ago" --no-pager -n 250 -q \
  | grep -E 'symphony_started|reconcile_startup_(begin|done|failed)|run_reconcile_(begin|done|failed)|dispatch_completed|rpc_orphan_reap_done|pi_rpc_probe_(ok|failed)|ERROR|Traceback'
```

Note: the reconcile/dispatch lines can lag `symphony_started` by up to ~90s (a startup probe runs first); the service shows `active/running` throughout. If the first grep shows only `symphony_started` + probe lines, wait and re-run before calling it stalled. To scope a re-run to the new process, add `_PID=<MainPID>` to the `journalctl` call.

Expected evidence:

- one `symphony_started service=symphony code_sha=<sha> bindings=<N>` line.
- one `reconcile_startup_begin` and matching `reconcile_startup_done` per binding.
- `run_reconcile_begin` / `run_reconcile_done` for Podium bindings when run reconciliation is enabled.
- at least one `dispatch_completed` line showing the scheduler loop is alive.
- **`rpc_orphan_reap_done count=<N>`** — the boot orphan sweep ran (`count=0` is the healthy steady state).
- **`pi_rpc_probe_ok`** when any binding sets `pi_mode: rpc`. A `pi_rpc_probe_failed reason=...` means the RPC binary/protocol is broken and RPC dispatch will fail — investigate before relying on RPC.
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
