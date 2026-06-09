---
title: Symphony Automation Runbook (homelab)
type: source-summary
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - wiki/raw/runbook-symphony.md
  - ~/homelab/docs/runbooks/automation/symphony.md
confidence: high
tags: [operations, runbook, homelab, telegram, blocked-reconciler]
---

# Source Summary — Symphony Automation Runbook

## What it is

Operational runbook for Symphony as deployed against the homelab Binding. Lives in the homelab repo at `~/homelab/docs/runbooks/automation/symphony.md`. Covers status checks, safe change workflow, smoke evidence, ticket scheduling, blocked reconciler, Telegram notifications, common failure pointers [source: wiki/raw/runbook-symphony.md].

## Major sections

- **Overview** — Symphony is the live automation bridge: Temporal patrols create Plane Todo tickets, Symphony polls and dispatches via `pi --print --no-session` against `/home/james/homelab` [source: wiki/raw/runbook-symphony.md#7-13].
- **Prerequisites** — paths to Plane stack, Symphony repo, homelab repo, service unit, env files. Do not print secret values [source: wiki/raw/runbook-symphony.md#17-24].
- **Read-Only Status Check** — `systemctl show` + `journalctl -u symphony-host.service` + temporal worker checks. Expected idle: `tick_completed dispatched=false reason=no-candidates` [source: wiki/raw/runbook-symphony.md#28-44].
- **Safe Change Workflow** — `python3 -m pytest` and `git diff --check` for Symphony; `uv run pytest tests/test_patrol_*.py` for homelab integration [source: wiki/raw/runbook-symphony.md#48-62].
- **Live Operations** — autonomous healthcheck remediation may restart services with cooldowns; human approval required for `systemctl stop`, direct Plane mutations, smoke requeues, env edits, destructive actions [source: wiki/raw/runbook-symphony.md#68-84].
- **Smoke Test Evidence** — `issue_claimed`, `agent_started`, `tick_completed dispatched=true`, Plane reaches terminal state, comments exist, repo clean [source: wiki/raw/runbook-symphony.md#86-95].
- **Ticket Scheduling** — see [Symphony operations](../concepts/symphony-operations.md) for the maintenance-window rule.
- **Blocked Reconciler** — three env vars (`SYMPHONY_BLOCKED_RECONCILER_ENABLED|APPLY|INTERVAL_MS`), dry-run default, evidence contract: counts distinct `Patrol pass for ...` comments newer than the latest failure [source: wiki/raw/runbook-symphony.md#136-197].
- **Telegram Notifications** — fire-and-forget on IN_REVIEW and BLOCKED transitions; configured via `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` or `TELEGRAM_HOME_CHANNEL` [source: wiki/raw/runbook-symphony.md#199-235].
- **Common Failure Pointers** — env names only; 401 = missing `X-API-Key`; 404 = use UUID not slug; 429 = cap pagination; `worktree_dirty` = inspect `/home/james/homelab`; missing comments = Plane write paths need trailing slashes [source: wiki/raw/runbook-symphony.md#237-244].

## Related wiki pages

- [Symphony operations](../concepts/symphony-operations.md) — distilled operational model
- [Symphony engine](../concepts/symphony-engine.md) — engine model
- [homelab Binding](../entities/binding-homelab.md)
