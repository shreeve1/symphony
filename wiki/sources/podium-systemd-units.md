---
title: Podium systemd units
type: source
status: promoted
created: 2026-06-11
updated: 2026-06-12
sources:
  - wiki/raw/podium-api.service
  - wiki/raw/podium-web.service
  - wiki/raw/telegram-alert@.service
  - wiki/raw/send-telegram-systemd-alert
  - wiki/raw/sessions/2026-06-11-podium-023d-trading-plane-archive.md
confidence: high
tags: [podium, systemd, operations, telegram]
---

# Podium systemd units

Snapshot of the live Podium service units and their failure-alert template after issue #023a actionable review.

## Units

`podium-api.service` runs FastAPI from `/home/james/symphony/web/api` with `/usr/bin/python3 -m uvicorn main:app --host 127.0.0.1 --port 8090 --workers 1`, loads `/home/james/symphony-host.env`, restarts on failure, and wires `OnFailure=telegram-alert@%n.service` [source: wiki/raw/podium-api.service].

`podium-web.service` runs Next.js from `/home/james/symphony/web/frontend` with `/usr/bin/pnpm start -p 8091`, loads `/home/james/symphony-host.env`, restarts on failure, and wires `OnFailure=telegram-alert@%n.service` [source: wiki/raw/podium-web.service]. The `start` script is `next start -H ${HOST:-0.0.0.0} -p 8091`, so the unit's `HOST` env selects the bind interface.

**Live update (2026-06-12, #023d):** `Environment=HOST=127.0.0.1` was changed to `Environment=HOST=10.20.20.16` so the frontend listens on the LAN interface for the `podium.testytech.net` reverse proxy. Verified: `10.20.20.16:8091` returns HTTP 200, loopback `127.0.0.1:8091` no longer answers. The raw snapshot still shows the old value (see its drift note); pre-change backup is `podium-web.service.bak.2026-06-12`. See C-0109. The API (`podium-api.service`) stays loopback on `127.0.0.1:8090`.

**Live update (2026-06-30, C-0354):** `podium-web.service` gained a drop-in at `/etc/systemd/system/podium-web.service.d/stop.conf` setting `KillSignal=SIGINT` + `TimeoutStopSec=10s`. `next-server` (Next.js 15) ignores both SIGTERM and SIGINT and will not shut down gracefully, so every stop/restart previously waited the full 90s default `TimeoutStopSec` then SIGKILL — which aborted `web/frontend/deploy.sh` mid-swap ("Job ... canceled", `set -e`) and flapped the unit back onto the old `.next` build. The 10s bound lets `systemctl stop` return rc=0 (unit goes `failed`/`Result=timeout` but a manual stop suppresses `Restart=on-failure`), so the deploy swap proceeds. ~10s web downtime per deploy is the accepted cost. Drop-in snapshot: `wiki/raw/podium-web.service.d-stop.conf`; reinstall must re-create it. See C-0354.

## Failure alert wiring

`telegram-alert@.service` is a oneshot unit that loads `/home/james/symphony-host.env` and executes `/usr/local/sbin/send-telegram-systemd-alert %i` [source: wiki/raw/telegram-alert@.service].

The alert script reads `TELEGRAM_BOT_TOKEN` plus `TELEGRAM_CHAT_ID` or `TELEGRAM_HOME_CHANNEL`, builds a message containing host, unit, and `systemctl show` state, then posts to Telegram Bot API. Missing env logs a skip and exits 0 [source: wiki/raw/send-telegram-systemd-alert].

## Verification convention

Unattended Ralph review should not fire live external notifications. For Podium failure-alert checks, verify unit `OnFailure` targets, template existence, executable alert script, and required env variable names rather than killing services to emit Telegram traffic [source: .kanban/issues/023a-podium-systemd-units.md].

## Claims

C-0103 in [CLAIMS.md](../CLAIMS.md).
