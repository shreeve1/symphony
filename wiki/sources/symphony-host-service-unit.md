---
title: symphony-host.service (live systemd unit snapshot)
type: source-summary
status: promoted
created: 2026-06-09
updated: 2026-06-15
sources:
  - wiki/raw/symphony-host.service
  - /etc/systemd/system/symphony-host.service
  - wiki/raw/sessions/2026-06-15-symphony-host-nonewprivileges.md
confidence: high
tags: [systemd, service, unit, environment, opencode-drift, lock-path, privileges]
---

# Source Summary — `symphony-host.service`

Live snapshot of the unit file on `aidev` as of 2026-06-09, with later drop-in drift noted. Path: `/etc/systemd/system/symphony-host.service`; current drop-in path: `/etc/systemd/system/symphony-host.service.d/override.conf`.

## Sections

### `[Unit]`

- `Description=Host-native Plane Symphony scheduler`
- `OnFailure=telegram-alert@%n.service` — failure-alert template fires on unit failure.
- `After=network-online.target` + `Wants=network-online.target` — waits for network.

### `[Service]`

- `Type=simple`
- `User=james`, `Group=james`
- `WorkingDirectory=/home/james/symphony` — `bindings.yml` auto-discovered at CWD per CLAUDE.md.
- `EnvironmentFile=/home/james/symphony-host.env` — secrets bag (mode `0600`).
- `ExecStart=/usr/bin/python3 -m main`
- `Restart=on-failure`, `RestartSec=10`
- Base unit still declares `NoNewPrivileges=yes`, but the live drop-in now overrides runtime to `NoNewPrivileges=no` as of 2026-06-15 [source: wiki/raw/sessions/2026-06-15-symphony-host-nonewprivileges.md#durable-facts].
- `PrivateTmp=yes`
- `RuntimeDirectory=symphony`, `RuntimeDirectoryMode=0750` — creates `/run/symphony/` owned by service user.

### `[Install]`

- `WantedBy=multi-user.target`

## `Environment=` block (non-secret config)

| Var | Value | Notes |
|---|---|---|
| `HOME` | `/home/james` | |
| `PYTHONUNBUFFERED` | `1` | structured log flushing |
| `PYTHONPATH` | `/home/james/symphony:/home/james/homelab/automation/homelab-stack/src` | homelab-stack still on path for compat |
| `OPENCODE_BIN` | `/home/james/.opencode/bin/opencode` | **DEAD** — pi-executor-swap landed; zero references in current `.py` source per CLAUDE.md |
| `SYMPHONY_LOCK_PATH` | `/run/symphony/symphony.lock` | overrides `config.py` default |
| `SYMPHONY_OPENCODE_AGENT` | `build` | **DEAD** — same as `OPENCODE_BIN` |
| `PLANE_API_URL` | `http://127.0.0.1:8000` | local Plane stack |
| `PLANE_WORKSPACE_SLUG` | `homelab` | only one workspace exists; all Bindings share it per CONTEXT.md |

[source: wiki/raw/symphony-host.service#13-20]

## What's NOT in the unit file

Secrets and runtime executor config live in `/home/james/symphony-host.env` and are loaded via `EnvironmentFile=`. Per CLAUDE.md "Required env vars (bindings mode)":

- `PLANE_API_KEY` — secret, must come from env file
- `PI_BIN` — required for executor dispatch
- `SYMPHONY_PI_PROVIDER` + `SYMPHONY_PI_MODEL` — non-secret but live in env file
- `ZAI_API_KEY` — pi's per-provider key (per brainstorm)
- Telegram tokens (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` / `TELEGRAM_HOME_CHANNEL`)
- Optional: `SYMPHONY_BLOCKED_RECONCILER_ENABLED|APPLY|INTERVAL_MS`, `PI_OFFLINE`, `PI_CODING_AGENT_SESSION_DIR`

`PLANE_PROJECT_ID` and `HOMELAB_REPO_PATH` are legacy single-project fallbacks per CLAUDE.md; bindings mode bypasses them.

## Notable drift

- `OPENCODE_BIN` and `SYMPHONY_OPENCODE_AGENT` survive on the unit despite the pi-executor swap (commit `8af5dab`). Documented in CLAUDE.md "Dead config" section. Safe to leave; safe to remove at a future unit cleanup.
- The brainstorm calls out that the swap requires removing these and adding `PI_BIN`, `SYMPHONY_PI_PROVIDER`, `SYMPHONY_PI_MODEL`, `PI_OFFLINE`, `PI_CODING_AGENT_SESSION_DIR` (the latter three optional). The `Environment=` block here did not get the additions — they live in the env file instead.

## 2026-06-15 privilege posture update

James chose the global option to disable the kernel no-new-privileges boundary for `symphony-host.service`. The base unit still contains `NoNewPrivileges=yes`, but `/etc/systemd/system/symphony-host.service.d/override.conf` now contains `NoNewPrivileges=no`, and live verification showed `MainPID=562675`, `NoNewPrivileges=no`, `ActiveState=active`, `SubState=running`, `ActiveEnterTimestamp=Mon 2026-06-15 00:25:08 UTC` [source: wiki/raw/sessions/2026-06-15-symphony-host-nonewprivileges.md#durable-facts].

This is a global scheduler posture, not a `symphony`-binding-only setting: agents launched for all bindings inherit it and can attempt `sudo` if sudoers permits [source: wiki/raw/sessions/2026-06-15-symphony-host-nonewprivileges.md#decisions]. The risk is highest for the `symphony` self-binding because those agents work in the scheduler repo itself [source: wiki/entities/binding-symphony.md#risk-posture].

## Restart safety

Per CLAUDE.md restart ritual: ask James → `sudo systemctl restart` → verify `symphony_started`, `reconcile_startup_*`, `dispatch_completed` log lines within ~35s. Use the `symphony-restart` skill rather than manual fallback.

## Related

- [Symphony operations](../concepts/symphony-operations.md)
- [Runbook source](runbook-symphony.md)
- [Plan history — pi-executor-swap](../analyses/symphony-plan-history.md)

> **2026-06-12 update:** `SYMPHONY_PI_PROVIDER`/`SYMPHONY_PI_MODEL` were removed from the unit's `override.conf` drop-in and the dead `OPENCODE_*` lines from the unit itself (backups `*.bak.2026-06-12`; daemon-reload + restart verified, startup pi probe now exercises the `models.yml` default). Podium dispatch reads `models.yml`. See [../analyses/podium-issue-dispatch-contract.md](../analyses/podium-issue-dispatch-contract.md).
