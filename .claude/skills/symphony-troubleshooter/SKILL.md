---
name: symphony-troubleshooter
description: Real-time Symphony diagnostic copilot for safe Podium-era log review, binding/run correlation, hypotheses, and handoffs. Read-only unless James pivots to another skill.
---

# Symphony Troubleshooter

Diagnose Symphony dispatch incidents without mutating live state. Use when the scheduler is not dispatching, a Podium Issue is stuck, a binding looks stale, a Run failed, or logs need interpretation.

## Scope

### Use for

- `symphony-host.service` health and scheduler liveness.
- Podium binding status and Issue/Run correlation.
- Startup reconcile and orphan Run reconcile evidence.
- Podium API/web reachability when needed for read-only context.
- Agent runner failures, silent exits, timeouts, blocked/review verdicts.
- Preparing a future-session handoff.

### Out of scope

- Restarting services. Hand off to `symphony-restart`.
- Creating smoke Issues. Hand off to `symphony-binding-smoke`.
- Creating/editing bindings. Hand off to `symphony-binding-scaffold`.
- Authoring repository `WORKFLOW.md`. Hand off to `symphony-workflow-author`.
- Legacy Plane archive/state repair. Hand off to `symphony-plane-recover` only for explicit retirement work.
- Unit-file edits, DB writes, Issue state changes, worktree deletion, or env edits.

## Safety rules

- Read-only by default.
- Never read or print `/home/james/symphony-host.env`.
- Never show secrets, request headers, cookies, or auth tokens.
- Never run `systemctl restart`, `start`, `stop`, `daemon-reload`, or service edits inside this skill.
- Never write Podium rows, Plane data, `bindings.yml`, worktrees, or issue states inside this skill.
- If the next useful action is mutation, stop and recommend the correct skill with evidence.

## Key locations

- Symphony repo: `/home/james/symphony/`
- Binding config: `/home/james/symphony/bindings.yml`
- Podium DB: `PODIUM_DB_PATH` or `/var/lib/symphony/podium.db` via `web.api.db.resolve_db_path()`
- Scheduler service: `symphony-host.service`
- Podium services: `podium-api.service`, `podium-web.service`
- Bound repos: read current paths from `bindings.yml`
- Run logs: beside the active Podium DB under `runs/` unless configured otherwise

## First response pattern

1. Ask for missing target: binding name, Issue id, Run id, or symptom.
2. State success criterion: identify whether this is service health, dispatch eligibility, Run failure, or tracker/UI drift.
3. Run bounded read-only checks.
4. Maintain 2-4 ranked hypotheses with one confirming check each.
5. Recommend wait, restart, smoke, workflow authoring, binding scaffold, legacy Plane recovery, or code diagnosis.

## Baseline checks

### Service snapshot

```bash
systemctl show symphony-host.service \
  --property=ActiveState,SubState,MainPID,ActiveEnterTimestamp,WorkingDirectory --no-pager
systemctl show podium-api.service podium-web.service \
  --property=ActiveState,SubState,MainPID,ActiveEnterTimestamp --no-pager
```

### Repo snapshot

```bash
git -C /home/james/symphony log --oneline -1
git -C /home/james/symphony status --porcelain
```

Do not treat a dirty tree as root cause by itself. It matters for restart safety.

### Binding config snapshot

```bash
python3 - <<'PY'
import yaml
path = "/home/james/symphony/bindings.yml"
data = yaml.safe_load(open(path, encoding="utf-8"))
bindings = data.get("bindings", data) if isinstance(data, dict) else data
for b in bindings:
    print(f"{b['name']}\ttracker={b.get('tracker','plane')}\trepo={b.get('repo_path','?')}\tagent={b.get('default_agent','pi')}\tbase={b.get('base_branch','?')}")
PY
```

### Podium API read-only status

Use only non-secret local endpoints. Important read endpoints: `GET /api/bindings`, `GET /api/bindings/{name}/issues`, `GET /api/issues/{issue_id}/runs`, and `GET /api/runs/{run_id}`. If auth blocks access, report that and switch to DB/journal evidence rather than reading secrets.

```bash
curl -fsS http://127.0.0.1:8090/api/health || true
curl -fsS http://127.0.0.1:8090/api/bindings || true
```

Per binding, when API auth/session is already available in the operator shell:

```bash
NAME=<binding>
curl -fsS "http://127.0.0.1:8090/api/bindings/$NAME/issues" || true
```

### Podium DB read-only fallback

```bash
cd /home/james/symphony
python3 - <<'PY'
from web.api.db import resolve_db_path
print(resolve_db_path())
PY
```

If James approves reading the local DB path and it is readable:

```bash
DB=<resolved-path>
sqlite3 "$DB" "select name, repo_path, default_agent from binding order by name;"
sqlite3 "$DB" "select id, binding_name, title, state, latest_run_state, latest_verdict, updated_at from issue order by updated_at desc limit 20;"
sqlite3 "$DB" "select id, issue_id, state, verdict, summary, updated_at from run order by updated_at desc limit 20;"
```

### Recent error slice

```bash
journalctl -u symphony-host.service --since=30m --no-pager \
  | grep -E 'ERROR|Traceback|ConfigError|reconcile_startup_failed|run_reconcile_failed|dispatch_failed|workflow-missing|permission-gate|approval-gate|pi_silent_exit|agent-crashed|timeout|nonzero|archived_terminal' \
  || echo "no recent matched scheduler errors"
```

### Lifecycle slice

```bash
journalctl -u symphony-host.service --since=30m --no-pager \
  | grep -E 'symphony_started|reconcile_startup_(begin|done|failed)|run_reconcile_(begin|done|failed)|dispatch_completed|issue_claimed|agent_exited|state_transitioned|run_record_(started|finished)|archived_terminal|log_retention_(begin|done|failed)' \
  | tail -160
```

### Per-target slices

```bash
NAME=<binding>
journalctl -u symphony-host.service --since=2h --no-pager \
  | grep -E "binding=$NAME|reconcile_startup_(begin|done|failed)|run_reconcile_(begin|done|failed)" \
  | tail -160

ISSUE_ID=<podium-issue-id>
journalctl -u symphony-host.service --since=2h --no-pager \
  | grep -E "issue_id=$ISSUE_ID|agent_exited|state_transitioned|dispatch_completed|archived_terminal" \
  | tail -160
```

## Common findings

### Service down

Evidence: `ActiveState` not active, startup traceback, or missing `symphony_started` after boot.

Action: capture `systemctl show` + last 80 journal lines. Recommend `symphony-restart` only after cause is understood.

### Running code stale

Evidence: disk SHA differs from latest `symphony_started code_sha`.

Action: recommend `symphony-restart`; do not restart inside this skill.

### Binding not eligible

Evidence: no candidate dispatch, missing `WORKFLOW.md`, archived/done/blocked state, approval or schedule gate, or wrong binding.

Action: correlate binding config, Podium Issue state, and prompt-renderer/workflow evidence. Hand off to `symphony-workflow-author` if workflow is missing or stubbed.

### Run failed or blocked

Evidence: latest Run has `state=failed`, `verdict=blocked`, timeout, nonzero exit, or `pi_silent_exit`.

Action: inspect Run summary/log path if readable; report root failure. Do not edit Issue state. Recommend operator reply, code diagnosis, or smoke depending on evidence.

### Archived terminal behavior

Evidence: `archived_terminal` log or Issue state `archived` while Run finishes.

Action: treat as intentional. The engine finalizes the Run row and skips Issue resurrection.

### Podium API/UI drift

Evidence: DB rows changed but UI stale, or WebSocket expectations not met.

Action: remember engine state surfaces by gated polling, not WebSocket push. Check API responses and frontend polling posture before blaming scheduler.

### Legacy Plane residue

Evidence: explicit old Plane archive or state-fill request.

Action: hand off to `symphony-plane-recover`. New binding work must use Podium skills.

## Handoff format

```text
SYMPHONY_TROUBLESHOOT_HANDOFF
symptom: <what James observed>
time_window: <journal/db/API window inspected>
service: symphony=<active/substate pid started> podium_api=<state> podium_web=<state>
code_sha: disk=<sha> running=<sha-or-unknown>
target: binding=<name-or-none> issue_id=<id-or-none> run_id=<id-or-none>
key_evidence:
  - <timestamp/source> <exact concise line>
  - <timestamp/source> <exact concise line>
hypotheses:
  1. <hypothesis> evidence=<...> next_check=<...>
  2. <hypothesis> evidence=<...> next_check=<...>
recommended_next: <wait|symphony-restart|symphony-binding-smoke|symphony-workflow-author|symphony-binding-scaffold|symphony-plane-recover|diagnose|operator reply>
safety_boundary: read-only; no env, service, DB, tracker, or worktree mutation performed
```

## Verification

Run:

```bash
cd /home/james/symphony && uv run pytest tests/skills/test_restart_troubleshooter.py
```
