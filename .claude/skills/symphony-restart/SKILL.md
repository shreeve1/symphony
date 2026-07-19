---
name: symphony-restart
description: Restart Symphony safely, with an explicit --full-stack branch that rebuilds/restarts Podium migrations, API, frontend, then the scheduler. Use after code or config changes, for stale processes, or when the operator requests a full Podium rebuild.
---

# Symphony Restart

Restart the host-native Symphony stack safely. Scheduler-only is the default; `--full-stack` rebuilds/restarts Podium first.

## Prerequisites

- Symphony repo at `/home/james/symphony`.
- Service unit `symphony-host.service` exists.
- Full-stack branch also requires `podium-migrations.service`, `podium-api.service`, `podium-web.service`, and `web/frontend/deploy.sh`.
- Journal reads are available. **On this host the invoking user is not in `adm`/`systemd-journal`, so plain `journalctl -u symphony-host.service` silently returns no service lines** (it prints a "you are not seeing messages from other users" hint and an empty result — running `code_sha` comes back unknown). Use **`sudo journalctl ... -q`** for every journal read in this skill; the `-q` suppresses the hint. If `sudo` is unavailable, report running-sha as `unknown (journal not readable)` rather than treating empty output as "no errors".
- `sudo systemctl restart symphony-host.service` is pre-approved (harness allow-rule + `CLAUDE.md`): run it without asking. Podium operations require `--full-stack`, `full rebuild`, or an explicit request to rebuild/restart Podium; that intent approves the Podium operations for that run only.

## Safety rules

- Scheduler restart is pre-approved. Podium migration/API restarts and `web/frontend/deploy.sh` require explicit James approval, supplied by an explicit full-stack request for that run.
- Never manually stop/start services, reload/edit units, alter database records, or roll back. The full-stack branch may apply checked-in Alembic migrations; `deploy.sh` owns the frontend stop/swap/start sequence.
- Never read or print `/home/james/symphony-host.env`.
- Never mutate Podium/Plane records, `bindings.yml`, issues, runs, or worktrees.
- If any stage fails, stop before downstream stages and report evidence; do not repair inside this skill.
- In scheduler-only mode, if disk head and running `symphony_started code_sha` match, say no restart is needed and ask whether James still wants one. An explicit full-stack request restarts every component.

## Workflow

### 1. Select scope

- Default: scheduler-only; do not touch Podium.
- Full stack: only for `--full-stack`, `full rebuild`, or an explicit request to rebuild/restart Podium. A read-only request that merely mentions Podium is not approval. Run Podium migrations → API → frontend → Symphony.

### 2. Pre-restart sanity

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
sudo journalctl -u symphony-host.service -g 'symphony_started' \
  -n 1 --no-pager -q
```

For full stack, also run:

```bash
systemctl show podium-migrations.service \
  --property=ActiveState,Result,ExecMainStatus --no-pager
systemctl show podium-api.service podium-web.service \
  --property=Id,ActiveState,SubState,MainPID,ActiveEnterTimestamp,WorkingDirectory --no-pager
curl -sS -o /dev/null -w 'api=%{http_code}\n' http://127.0.0.1:8090/api/health || true
curl -sS -o /dev/null -w 'web=%{http_code}\n' http://10.20.20.16:8091/ || true
sudo journalctl -u podium-migrations.service -u podium-api.service -u podium-web.service \
  --since="5 minutes ago" -n 120 --no-pager -q \
  | grep -E 'ERROR|Traceback|ConfigError|schema.*(drift|mismatch)|Failed' \
  || echo "no recent matched Podium errors"
```

Capture:

- disk head SHA and subject.
- working-tree state.
- service active/substate/PID/start time.
- latest running `code_sha` from `symphony_started`.
- recent matched error count.
- full stack: migration/API/web state, health HTTP codes, and recent Podium errors.

Optional full-suite tests if James asks for `--with-tests`:

```bash
uv run pytest -q
```

### 3. Sanity verdict

Report:

```text
disk head      <sha> <subject>
running sha    <sha from latest symphony_started> (matches | stale | unknown)
working tree   clean | dirty: <paths>
service state  active/running | <state>/<substate>
recent errors  none | <count> matched lines
tests          not run | passed | failed
podium         n/a | migrations=<state> api=<state>/<http> web=<state>/<http>
```

Stop if a service is unhealthy, recent errors are unexplained, or the tree has risky unrelated changes. Ask James before proceeding if the only issue is an expected dirty tree.

### 4. Rebuild and restart Podium (full stack only)

The API runs Python source directly and has no build step. Run each stage separately and stop immediately if its success check fails.

**Migrations:**

```bash
set -euo pipefail
cd /home/james/symphony
uv run pytest -q tests/test_alembic_baseline.py
sudo systemctl restart podium-migrations.service
systemctl is-active --quiet podium-migrations.service
[ "$(systemctl show podium-migrations.service --property=Result --value)" = success ]
[ "$(systemctl show podium-migrations.service --property=ExecMainStatus --value)" = 0 ]
```

**API:**

```bash
set -euo pipefail
sudo systemctl restart podium-api.service
sleep 5
systemctl is-active --quiet podium-api.service
[ "$(systemctl show podium-api.service --property=SubState --value)" = running ]
API_STATUS="$(curl -fsS -o /dev/null -w '%{http_code}' http://127.0.0.1:8090/api/health)"
[ "$API_STATUS" = 200 ]
API_LOG="$(sudo journalctl -u podium-api.service --since="1 minute ago" -n 100 --no-pager -q)"
printf '%s\n' "$API_LOG" | grep -E 'Uvicorn running|Application startup complete'
! printf '%s\n' "$API_LOG" | grep -Eq 'ERROR|Traceback|schema.*(drift|mismatch)'
```

**Frontend:**

```bash
set -euo pipefail
web/frontend/deploy.sh
systemctl is-active --quiet podium-web.service
[ "$(systemctl show podium-web.service --property=SubState --value)" = running ]
[ "$(curl -fsS -o /dev/null -w '%{http_code}' http://10.20.20.16:8091/)" = 200 ]
WEB_LOG="$(sudo journalctl -u podium-web.service --since="2 minutes ago" -n 100 --no-pager -q)"
printf '%s\n' "$WEB_LOG" | grep -E 'Ready'
! printf '%s\n' "$WEB_LOG" | grep -Eq 'ERROR|Traceback|Could not find a production build'
```

The frontend deploy script clears the build cache, builds to staging, swaps atomically, and restarts the web unit. Do not auto-rollback or continue to Symphony after any failed command or success check.

### 5. Scheduler restart decision

Restart is pre-approved — no y/n prompt. State the exact command and reason, then proceed:

```text
Running:
  sudo systemctl restart symphony-host.service

Reason: <stale code sha | config reload | manual operator request>
```

In scheduler-only mode, skip when disk head and running `code_sha` match and ask whether James still wants one. An explicit full-stack request proceeds.

### 6. Restart Symphony

```bash
sudo systemctl restart symphony-host.service
sleep 5
systemctl show symphony-host.service \
  --property=ActiveState,SubState,MainPID,ActiveEnterTimestamp --no-pager
```

Record the `MainPID` and `ActiveEnterTimestamp` from this output. Verification must stay scoped to these original values; a later replacement PID is a failed restart, not success.

If not active/running, capture last 80 lines and stop:

```bash
sudo journalctl -u symphony-host.service --since="1 minute ago" -n 80 --no-pager -q
```

### 7. Verify scheduler lifecycle

Wait for the first dispatch/reconcile cycle, substituting the PID and timestamp recorded in step 6 rather than re-reading them after the wait:

```bash
set -euo pipefail
sleep 35
[ "$(systemctl show symphony-host.service --property=MainPID --value)" = '<recorded MainPID>' ]
SCHED_LOG="$(sudo journalctl -u symphony-host.service _PID='<recorded MainPID>' \
  --since='<recorded ActiveEnterTimestamp>' --no-pager -n 250 -q)"
printf '%s\n' "$SCHED_LOG" | grep -E 'symphony_started'
printf '%s\n' "$SCHED_LOG" | grep -E 'rpc_orphan_reap_done'
! printf '%s\n' "$SCHED_LOG" \
  | grep -Eq 'ERROR|Traceback|reconcile_startup_failed|run_reconcile_failed|pi_rpc_probe_failed'
printf '%s\n' "$SCHED_LOG" \
  | grep -E 'symphony_started|reconcile_startup_(begin|done)|run_reconcile_(begin|done)|dispatch_completed|rpc_orphan_reap_done|pi_rpc_probe_ok'
```

Note: remote skill sync and reachability probes can delay reconciliation beyond 90s while the service remains `active/running`. If the first grep shows only startup/probe lines, wait and re-run the same original-PID/start-time-scoped command before calling it stalled.

Expected evidence:

- one `symphony_started service=symphony code_sha=<sha> bindings=<N>` line.
- one `reconcile_startup_begin` and matching `reconcile_startup_done` per binding.
- `run_reconcile_begin` / `run_reconcile_done` for Podium bindings when run reconciliation is enabled.
- at least one `dispatch_completed` line showing the scheduler loop is alive.
- **`rpc_orphan_reap_done count=<N>`** — the boot orphan sweep ran (`count=0` is the healthy steady state).
- **`pi_rpc_probe_ok`** when any binding sets `pi_mode: rpc`. A `pi_rpc_probe_failed reason=...` means the RPC binary/protocol is broken and RPC dispatch will fail — investigate before relying on RPC.
- zero `ERROR` / `Traceback` / `reconcile_startup_failed` lines since restart.

### 8. Verdict

Report:

```text
podium         n/a | migrations=ok api=ok web=ok
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
