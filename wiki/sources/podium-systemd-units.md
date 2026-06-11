---
title: Podium systemd units
type: source
status: promoted
created: 2026-06-11
updated: 2026-06-11
sources:
  - wiki/raw/podium-api.service
  - wiki/raw/podium-web.service
  - wiki/raw/telegram-alert@.service
  - wiki/raw/send-telegram-systemd-alert
confidence: high
tags: [podium, systemd, operations, telegram]
---

# Podium systemd units

Snapshot of the live Podium service units and their failure-alert template after issue #023a actionable review.

## Units

`podium-api.service` runs FastAPI from `/home/james/symphony/web/api` with `/usr/bin/python3 -m uvicorn main:app --host 127.0.0.1 --port 8090 --workers 1`, loads `/home/james/symphony-host.env`, restarts on failure, and wires `OnFailure=telegram-alert@%n.service` [source: wiki/raw/podium-api.service].

`podium-web.service` runs Next.js from `/home/james/symphony/web/frontend` with `/usr/bin/pnpm start -p 8091`, sets `HOST=127.0.0.1`, loads `/home/james/symphony-host.env`, restarts on failure, and wires `OnFailure=telegram-alert@%n.service` [source: wiki/raw/podium-web.service].

## Failure alert wiring

`telegram-alert@.service` is a oneshot unit that loads `/home/james/symphony-host.env` and executes `/usr/local/sbin/send-telegram-systemd-alert %i` [source: wiki/raw/telegram-alert@.service].

The alert script reads `TELEGRAM_BOT_TOKEN` plus `TELEGRAM_CHAT_ID` or `TELEGRAM_HOME_CHANNEL`, builds a message containing host, unit, and `systemctl show` state, then posts to Telegram Bot API. Missing env logs a skip and exits 0 [source: wiki/raw/send-telegram-systemd-alert].

## Verification convention

Unattended Ralph review should not fire live external notifications. For Podium failure-alert checks, verify unit `OnFailure` targets, template existence, executable alert script, and required env variable names rather than killing services to emit Telegram traffic [source: .kanban/issues/023a-podium-systemd-units.md].

## Claims

C-0103 in [CLAIMS.md](../CLAIMS.md).
