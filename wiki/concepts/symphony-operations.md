---
title: Symphony operations
type: concept
status: promoted
created: 2026-06-09
updated: 2026-07-16
sources:
  - wiki/raw/runbook-symphony.md
  - wiki/raw/symphony-context.md
  - wiki/raw/sessions/2026-06-15-symphony-host-nonewprivileges.md
confidence: high
tags: [operations, runbook, blocked-reconciler, telegram, scheduling, troubleshooting, privileges]
---

# Symphony operations

Distilled operational model for `symphony-host.service` on `aidev`. Source: homelab runbook + Symphony CLAUDE.md + CONTEXT.md.

## Service

- Unit: `/etc/systemd/system/symphony-host.service` runs `/usr/bin/python3 -m main` from `/home/james/symphony`.
- Working directory: `/home/james/symphony`; `bindings.yml` auto-discovered at CWD.
- Secrets env file: `/home/james/symphony-host.env` (mode `0600`; never print contents).
- Failure alert: `OnFailure=telegram-alert@%n.service`.
- Lock file: `SYMPHONY_LOCK_PATH=/run/symphony/symphony.lock`.
- Privilege posture as of 2026-06-15: live `symphony-host.service` runs with `NoNewPrivileges=no` via its `override.conf` drop-in, even though the base unit still declares `NoNewPrivileges=yes` [source: wiki/raw/sessions/2026-06-15-symphony-host-nonewprivileges.md#durable-facts].

## Expected idle state

`active` / `running`; logs show `tick_completed dispatched=false reason=no-candidates issue_id=` when no Todo tickets are ready [source: wiki/raw/runbook-symphony.md#38-42].

## Tick lifecycle (one binding)

`reconcile_startup_(begin|done|failed)` once per binding on startup → repeating `dispatch_completed` lines for liveness [source: CLAUDE.md, wiki/raw/runbook-symphony.md].

## Restart ritual

Use the `symphony-restart` skill: pre-sanity → ask James → restart → verify-log-lines (`symphony_started`, `reconcile_startup_*`, `dispatch_completed`). With remote bindings, scope the journal to the new PID and wait through `skill_sync_done` plus `remote_repo_reachable`: the 2026-07-16 restart did not begin reconciliation until about 148 seconds after `symphony_started`, so a 90-second wait is not a stall verdict [source: wiki/raw/sessions/2026-07-16-symphony-restart-remote-startup-delay.md#durable-facts].

Autonomous healthcheck remediation may restart `symphony-host.service` and `homelab-temporal-patrol-worker.service` with cooldowns and post-restart verification. Human approval is required for `systemctl stop`, non-remediation changes, direct Plane mutations outside approved automation, Temporal schedule changes, smoke requeues, env edits, destructive actions [source: wiki/raw/runbook-symphony.md#68-75].

## Agent sudo posture

Before 2026-06-15, agents launched by `symphony-host.service` inherited `NoNewPrivileges=yes`, so `sudo systemctl ...` failed inside runs even when the operator wanted a restart. Run #33 in the `symphony` binding hit this while trying to restart `podium-web.service` after a clean frontend rebuild [source: wiki/raw/sessions/2026-06-15-symphony-host-nonewprivileges.md#durable-facts].

James accepted the global safety tradeoff and changed the live service to `NoNewPrivileges=no`. This is not scoped per binding: all scheduler-dispatched agents can now attempt sudo-backed service or system changes if sudoers permits. The `symphony` self-binding has the largest blast radius because it can modify the scheduler repo while running under this broader privilege posture [source: wiki/raw/sessions/2026-06-15-symphony-host-nonewprivileges.md#decisions].

Policy gates still matter. Unit edits, service restarts/stops, Plane mutations, smoke requeues, env edits, and destructive operations still require James approval per project instructions; the kernel no-new-privileges flag no longer enforces that boundary for scheduler-launched agents [source: CLAUDE.md#safety].

## Ticket scheduling

One-shot ticket scheduling only; recurring patrol work belongs in Temporal schedules on `aidev`, not in Symphony.

Agent-created schedules use the injected Plane CLI [source: wiki/raw/runbook-symphony.md#117-120]:

```bash
plane schedule --not-before <iso8601-with-offset> --reason <text> [--not-after <iso8601-with-offset>]
plane unschedule --reason <text>
```

James can schedule manually by adding only the Plane `scheduled` label to a Todo ticket. When no `Symphony-Schedule:` comment exists, Symphony assumes the next **12am-6am America/Los_Angeles** maintenance window. If current local time is within that window, the ticket is eligible immediately and receives schedule context using that same window. Outside that window, the ticket is held silently — not blocked for missing schedule comment [source: wiki/raw/runbook-symphony.md#122].

Explicit schedule comments take precedence over the label-only fallback. Malformed controlling schedule comments block loudly; cancellation comments repair stale `scheduled` labels [source: wiki/raw/runbook-symphony.md#124].

## Blocked reconciler

Purpose: Symphony normally works Todo tickets only, but patrol tickets can end up in Blocked after transient failures. The reconciler scans Blocked and moves cured patrol tickets to Done when apply mode is enabled [source: wiki/raw/runbook-symphony.md#140-144].

Env config (lives in `/home/james/symphony-host.env`):

| Variable | Default | Effect |
|---|---|---|
| `SYMPHONY_BLOCKED_RECONCILER_ENABLED` | `true` | `false` disables scan entirely |
| `SYMPHONY_BLOCKED_RECONCILER_APPLY` | `false` | `false` logs only; `true` mutates Plane |
| `SYMPHONY_BLOCKED_RECONCILER_INTERVAL_MS` | `1800000` (30 min) | scan interval; first tick after start runs immediately |

Evidence contract: counts distinct `Patrol pass for ...` comments newer than the latest failure comment. Does not trust `consecutive_passes=N` (diagnostic only). Tickets with `approval-required` are skipped. Comment fetches paginated and capped [source: wiki/raw/runbook-symphony.md#160-166].

Expected logs: `blocked_reconcile_skipped|would_apply|applied|page_limit_reached|comment_page_limit_reached`.

Safe enable flow: verify dry-run candidates first → set `APPLY=true` → restart after approval → verify next tick.

## Telegram notifications

Issue-transition Telegram notifications are disabled by default. `main.py` only creates and passes `TelegramNotifier` into the scheduler when `SYMPHONY_ISSUE_TELEGRAM_NOTIFICATIONS` is truthy; otherwise IN_REVIEW/BLOCKED scheduler notifications short-circuit because `notifier=None`. `agent_runner.py` also withholds Telegram credentials from launched agents by default, and `plane_cli.py` refuses to send `plane review` / `plane blocked` Telegram messages unless the same opt-in flag is present [source: main.py, agent_runner.py, plane_cli.py].

When the opt-in is enabled, issue notifications remain fire-and-forget for **IN_REVIEW** and **BLOCKED** transitions only; scheduled and released ticket notifications stay intentionally disabled to reduce noise [source: wiki/raw/runbook-symphony.md#199-201]. The systemd `OnFailure=telegram-alert@%n.service` failure-alert path is separate and unchanged [source: wiki/raw/send-telegram-systemd-alert].

Architecture: `notifier.py` (`TelegramNotifier` class, async `send` + sync `send_sync`); `scheduler.py` calls after transitions when passed a notifier; `plane_cli.py` sends on `plane review` and `plane blocked` commands only under the opt-in flag. Failures log warnings, never block scheduler [source: wiki/raw/runbook-symphony.md#205-208, main.py, plane_cli.py].

Config env (from `/home/james/symphony-host.env`):

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | Bot API token |
| `TELEGRAM_CHAT_ID` | one of two | preferred chat target |
| `TELEGRAM_HOME_CHANNEL` | one of two | fallback chat target |
| `PLANE_FRONTEND_URL` | optional | issue links |
| `PLANE_DASHBOARD_URL` | optional | dashboard link |
| `SYMPHONY_ISSUE_TELEGRAM_NOTIFICATIONS` | no | truthy opt-in for issue-transition Telegram notifications; default disabled |

Startup logs confirm `issue_telegram_notifications_enabled` or `issue_telegram_notifications_disabled` [source: main.py].

Message format: `📋 <b>IDENT</b>: Name → <b>Review</b>` or `🚫 <b>IDENT</b>: Name → <b>Blocked</b>` with optional reason and links.

## Common failure pointers

| Symptom | Likely cause |
|---|---|
| `401 Unauthorized` | Plane local API expects `X-API-Key` |
| `404 Not Found` | verify project UUID, not slug-like ID |
| `429 Too Many Requests` | pagination not capped |
| `worktree_dirty` log | inspect bound repo before dispatch |
| missing comments | Plane write paths need trailing slashes |
| missing env | inspect variable names only; do not print values |

[source: wiki/raw/runbook-symphony.md#237-244]

## Related wiki pages

- [Runbook source summary](../sources/runbook-symphony.md)
- [Symphony engine](symphony-engine.md)
- [homelab Binding](../entities/binding-homelab.md)
