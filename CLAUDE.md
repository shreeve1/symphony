# Symphony — Agent Context

This is the Symphony host-native scheduler source repo. It is live infrastructure: `symphony-host.service` runs `/usr/bin/python3 -m main` from this directory and polls Plane for Todo tickets.

## Key Paths

- `/home/james/symphony/` — this repo. `bindings.yml` lives at the root; auto-discovered at CWD.
- `/home/james/symphony-host.env` — secrets (`PLANE_API_KEY`, etc.). File mode `0600`; never `cat` or print contents.
- `/etc/systemd/system/symphony-host.service` — service unit. `OnFailure=telegram-alert@%n.service`.
- `/etc/systemd/system/telegram-alert@.service` — failure-alert template; shares the same env file.
- `/home/james/homelab/` and `/home/james/trading/crypto-trading-agents` — repos Symphony agents inspect and modify (per `bindings.yml`).
- `/home/james/homelab/docs/runbooks/automation/symphony.md` — project runbook.

## Safety

- Treat as live infrastructure.
- Do not print values from `/home/james/symphony-host.env`.
- Ask James before `systemctl restart`, `stop`, unit edits, Plane API mutations, or smoke ticket requeues unless he has already approved that exact live mutation.

## Env locations

- `/home/james/symphony-host.env` — secret values (`PLANE_API_KEY`, etc.).
- `symphony-host.service` `Environment=` — non-secret config (`PLANE_API_URL`, `PLANE_WORKSPACE_SLUG`, `PI_BIN`, `SYMPHONY_PI_PROVIDER`, `SYMPHONY_PI_MODEL`). Inspect with `systemctl show symphony-host.service --property=Environment`.
- `WorkingDirectory=/home/james/symphony` — `bindings.yml` auto-discovered at cwd; `SYMPHONY_BINDINGS_PATH` not required.

## Required env vars (bindings mode)

- `PLANE_API_URL`
- `PLANE_API_KEY`
- `PLANE_WORKSPACE_SLUG`
- `PI_BIN`

`PLANE_PROJECT_ID` and `HOMELAB_REPO_PATH` may still be set on the unit — harmless, ignored in bindings mode.

## Dead config

`Environment=OPENCODE_BIN=...` and `Environment=SYMPHONY_OPENCODE_AGENT=build` on `symphony-host.service` are unreferenced by current code and survive only as drift. Safe to leave; safe to remove at a future unit cleanup.

## Live bindings

Source of truth: `/home/james/symphony/bindings.yml`.

| name | repo |
|---|---|
| `homelab` | `/home/james/homelab` |
| `trading` | `/home/james/trading/crypto-trading-agents` |

## Common log queries

```bash
# Reconcile lifecycle (one pair per binding)
journalctl -u symphony-host.service --since=5m -n 200 --no-pager \
  | grep -E 'reconcile_startup_(begin|done|failed)'

# Dispatch loop liveness
journalctl -u symphony-host.service --since=2m -n 100 --no-pager \
  | grep 'dispatch_completed'

# Filter by binding
journalctl -u symphony-host.service --since=10m --no-pager | grep 'binding=trading'

# Errors only
journalctl -u symphony-host.service --since=15m --no-pager \
  | grep -E 'ERROR|Traceback|ConfigError'
```

## Service unit

Path: `/etc/systemd/system/symphony-host.service`. If editing, back up first (`sudo cp <unit> <unit>.bak.<date>`) and `systemctl daemon-reload` before restart. Ask James before any unit edit.

## Restart ritual

Use the `symphony-restart` skill — wraps pre-sanity, ask-then-restart, and post-restart log verification (`symphony_started`, `reconcile_startup_*`, `dispatch_completed`).

Manual fallback:

```bash
# pre-sanity
git -C /home/james/symphony log --oneline -1
git -C /home/james/symphony status --porcelain
systemctl show symphony-host.service --property=ActiveState,MainPID,ActiveEnterTimestamp

# restart (ask James first)
sudo systemctl restart symphony-host.service
sleep 5 && systemctl is-active symphony-host.service
sleep 35
journalctl -u symphony-host.service --since="1 minute ago" --no-pager \
  | grep -E 'symphony_started|reconcile_startup_(begin|done)|dispatch_completed'
```

## Quick Checks

Run from `/home/james/symphony`:

```bash
git status --porcelain
python3 -m pytest
```

Run for the host-native Symphony service:

```bash
systemctl show symphony-host.service --property=ActiveState,SubState,MainPID,ActiveEnterTimestamp,WorkingDirectory --no-pager
journalctl -u symphony-host.service --since=5m --no-pager -n 100
```

## Skill suite

- `symphony-project-scaffold` — create a Plane project + binding entry.
- `symphony-workflow-author` — replace a binding's stub WORKFLOW.md with a real one.
- `symphony-restart` — pre-sanity → ask → restart → verify.
- `symphony-bindings-status` — read-only "what's running" table.
- `symphony-binding-smoke` — file a low-risk smoke ticket, watch one Run.
- `symphony-plane-recover` — archive / state-fill for half-built projects.
- `symphony-onboard-project` — umbrella that chains the above.
