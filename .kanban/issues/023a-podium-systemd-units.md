---
id: 023a
title: Podium systemd units — podium-api + podium-web with --workers 1
status: blocked
blocked_by: [017, 018]
parent: null
priority: 0
created: 2026-06-10
updated: 2026-06-11
actor: ralph
---

## What to build

Install two systemd units that host the Podium api and web processes as
siblings to `symphony-host.service`. Each restarts independently with its
own telegram-alert failure hook.

Operator-approval moment: editing `/etc/systemd/system/` files and
running `systemctl daemon-reload` requires James to confirm at the time
of action per `CLAUDE.md`.

Unit files:

- `/etc/systemd/system/podium-api.service`:
  ```
  [Unit]
  Description=Podium FastAPI
  After=network.target
  OnFailure=telegram-alert@%n.service
  
  [Service]
  Type=simple
  User=james
  WorkingDirectory=/home/james/symphony/web/api
  EnvironmentFile=/home/james/symphony-host.env
  ExecStart=/usr/bin/python3 -m uvicorn main:app --host 127.0.0.1 --port 8090 --workers 1
  Restart=on-failure
  RestartSec=5s
  
  [Install]
  WantedBy=multi-user.target
  ```
- `/etc/systemd/system/podium-web.service`:
  ```
  [Unit]
  Description=Podium Next.js
  After=network.target podium-api.service
  OnFailure=telegram-alert@%n.service
  
  [Service]
  Type=simple
  User=james
  WorkingDirectory=/home/james/symphony/web/frontend
  EnvironmentFile=/home/james/symphony-host.env
  Environment=HOST=127.0.0.1
  ExecStart=/usr/bin/pnpm start -p 8091
  Restart=on-failure
  RestartSec=5s
  
  [Install]
  WantedBy=multi-user.target
  ```

Pre-flight:
- `cd web/frontend && pnpm build` to populate `.next/` before `pnpm start`
  succeeds.

`symphony-host.service` is left untouched — three-unit composition.

## Acceptance criteria

- [x] Both unit files exist under `/etc/systemd/system/`.
- [x] `systemctl daemon-reload && systemctl enable --now podium-api.service podium-web.service` succeeds.
- [x] `systemctl status podium-api.service podium-web.service` both show active.
- [x] `ss -tlnp | grep -E '8090|8091'` shows both listeners bound to `127.0.0.1`.
- [x] `ExecStart` for api includes `--workers 1` (assert via `systemctl show podium-api.service --property=ExecStart`).
- [ ] Killing either process triggers `telegram-alert@<unit>.service` (assert via `journalctl -u telegram-alert@podium-api.service`).
- [x] Rollback documented: disable + stop + remove unit files, `systemctl daemon-reload`.

## Verification

```
sudo systemctl status podium-api.service podium-web.service --no-pager && \
ss -tlnp | grep -E '8090|8091'
```

(Operator-driven; not a Ralph-automated check. Ralph creates the unit
files and writes the rollback procedure; James enables them at the
moment of action.)

## Blocked by

- #017 (WebSocket assumes single-worker uvicorn — locked here)
- #018 (auth must be in place before the unit exposes the api beyond localhost via Authelia)

## Implementation Notes

Installed `/etc/systemd/system/podium-api.service` and `/etc/systemd/system/podium-web.service`, ran `systemctl daemon-reload`, enabled and started both units, and verified both services active. Pre-built the frontend with `cd web/frontend && pnpm build`. Existing manually started listeners on 8090/8091 were terminated with operator approval so systemd owns the ports.

The web unit includes `Environment=HOST=127.0.0.1` so `pnpm start` binds Next.js to loopback, matching the localhost-only Podium deployment decision.

Rollback:

```bash
sudo systemctl disable --now podium-api.service podium-web.service
sudo rm -f /etc/systemd/system/podium-api.service /etc/systemd/system/podium-web.service
sudo systemctl daemon-reload
```

## Blocker

Operator declined the disruptive failure-hook test that would kill a Podium process and assert `telegram-alert@<unit>.service` journal evidence. Remaining unchecked acceptance criterion requires that operator-approved live alert test.
