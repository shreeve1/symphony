# Symphony Automation Runbook

Purpose: help future sessions understand and safely operate Symphony, the service that turns Plane Todo tickets into `pi` agent work against the homelab repo.

## Overview

Symphony is the live automation bridge for this homelab:

- Temporal patrol schedules create or update Plane Todo tickets through the homelab patrol worker.
- `symphony-host.service` runs the host-native Symphony scheduler from `/home/james/symphony` and polls Plane for eligible Todo tickets.
- Symphony claims one ticket, runs `pi --print --no-session` in `/home/james/homelab`, and updates Plane state/comments.
- As of 2026-05-23, the active Temporal patrol worker process runs under `homelab-temporal-patrol-worker.service` as `.venv/bin/python -m homelab_worker.worker` from `/home/james/homelab/automation/homelab-stack`; `symphony-host.service` handles Plane ticket polling only.
- Runtime executor settings live in `symphony-host.service`: `PI_BIN`, `SYMPHONY_PI_PROVIDER`, and `SYMPHONY_PI_MODEL`.

## Prerequisites

- Plane stack root: `/home/james/plane`.
- Symphony source repo: `/home/james/symphony`.
- Homelab source repo: `/home/james/homelab`.
- Live host unit: `symphony-host.service`.
- Plane live compose file: `/home/james/plane/docker-compose.yml`.
- Secret-bearing env files: `/home/james/plane/variables.env` and `/home/james/homelab/.env`.

Do not print secret values. Check only variable names or boolean presence when diagnosing environment issues.

## Read-Only Status Check

Run on `aidev`:

```bash
systemctl show symphony-host.service --property=ActiveState,SubState,MainPID,ActiveEnterTimestamp,WorkingDirectory --no-pager
journalctl -u symphony-host.service --since=5m --no-pager
systemctl show homelab-temporal-patrol-worker.service --property=ActiveState,SubState,MainPID,ActiveEnterTimestamp,WorkingDirectory --no-pager
pgrep -af "homelab_worker.worker|python -m homelab_worker.worker" || true
for p in $(pgrep -f "homelab_worker.worker|python -m homelab_worker.worker" || true); do printf "%s " "$p"; cat /proc/$p/cgroup; done
```

Expected idle state:

- `symphony-host.service` is `active` / `running`.
- Logs show Plane requests returning `200 OK`.
- Logs show `tick_completed dispatched=false reason=no-candidates issue_id=` when no Todo tickets are ready.
- `homelab-temporal-patrol-worker.service` is `active` / `running`.
- The Temporal patrol worker process is present and its cgroup is `/system.slice/homelab-temporal-patrol-worker.service`.

## Safe Change Workflow

For Symphony code changes, work in `/home/james/symphony`:

```bash
python3 -m pytest
git diff --check
```

For homelab integration changes, work in `/home/james/homelab/automation/homelab-stack`:

```bash
uv run pytest tests/test_patrol_plane.py tests/test_patrol_models.py tests/test_patrol_checks_remaining.py tests/test_patrol_checks_docker.py
git diff --check
```

Active patrol behavior lives in the Temporal worker path under `src/homelab_worker/`.

For Docker wiring, remember `/home/james/plane/docker-compose.yml` is live on-disk configuration and is not in a git repo.

## Live Operations

Autonomous healthcheck remediation may restart `symphony-host.service` and `homelab-temporal-patrol-worker.service` when watchdogs detect unhealthy service/worker state, with cooldowns and post-restart verification. Human approval is still required for:

- `systemctl stop` or non-remediation service changes.
- Direct Plane `PATCH` or `POST` calls outside approved automation.
- Temporal patrol live triggers, schedule pauses, or broad schedule changes.
- Smoke ticket requeueing.
- Editing `.env` files.
- Destructive actions, data deletion, or unscheduled reboots.

After approved restart, verify:

```bash
systemctl restart symphony-host.service
systemctl show symphony-host.service --property=ActiveState,SubState,MainPID,ActiveEnterTimestamp --no-pager
journalctl -u symphony-host.service --since=2m --no-pager
pgrep -af "homelab_worker.worker|python -m homelab_worker.worker" || true
```

## Smoke Test Evidence

A successful read-only smoke should show:

- The Plane smoke issue starts as Todo.
- Logs show `issue_claimed` and `agent_started`.
- Logs show `tick_completed dispatched=true`.
- The Plane issue reaches Done, In Review, or Blocked intentionally.
- Claim and terminal summary comments exist.
- `/home/james/homelab` remains clean for read-only smoke.

## Ticket Scheduling

Safety label: Human-gated for live Plane mutations. Read-only code and test checks are safe.

Symphony supports one-shot ticket scheduling only. Recurring patrol work belongs in Temporal schedules on `aidev`, not in Symphony's ticket scheduler.

Temporal patrol schedules currently target `PatrolWorkflow` on task queue `homelab-runbooks`. The active worker process is `.venv/bin/python -m homelab_worker.worker`; as of 2026-05-23 it runs under `homelab-temporal-patrol-worker.service`.

For patrol ticket behavior changes, edit the Temporal patrol code first: `src/homelab_worker/patrol_models.py`, `src/homelab_worker/patrol_plane.py`, and the domain checks under `src/homelab_worker/patrol_checks/`.

Verify recurring patrol ownership from `/home/james/homelab/automation/homelab-stack`:

```bash
.venv/bin/python -m homelab_worker.schedule_patrols describe --live --temporal-host 10.20.20.16:7233 --temporal-namespace default
ssh james@10.20.20.16 'systemctl show homelab-temporal-patrol-worker.service --property=ActiveState,SubState,MainPID,ActiveEnterTimestamp --no-pager'
ssh james@10.20.20.16 'pgrep -af "homelab_worker.worker|python -m homelab_worker.worker" || true'
```

Agent-created schedules should use the injected Plane CLI:

```bash
plane schedule --not-before <iso8601-with-offset> --reason <text> [--not-after <iso8601-with-offset>]
plane unschedule --reason <text>
```

James can schedule manually by adding only the Plane `scheduled` label to a Todo ticket. When no `Symphony-Schedule:` comment exists, Symphony assumes the next 12am-6am America/Los_Angeles maintenance window. If the current local time is within that window, the ticket is eligible immediately and receives schedule context using that same window. Outside that window, the ticket is held silently; it is not blocked for a missing schedule comment.

Explicit schedule comments still take precedence over the label-only fallback. Malformed controlling schedule comments block loudly, and cancellation comments repair stale `scheduled` labels.

Verify scheduling changes without live Plane mutations:

```bash
cd /home/james/symphony
python3 -m pytest tests/test_schedule.py tests/test_plane_cli.py tests/test_plane_poller.py tests/test_scheduler.py tests/test_notifier.py -q
python3 -m pytest -q
python3 -m py_compile *.py
git diff --check
```

## Blocked Reconciler

Safety label: Dry-run by default. Do not enable apply mode until dry-run logs show plausible `blocked_reconcile_would_apply` candidates.

Purpose:

- Symphony normally works Todo tickets only.
- Patrol tickets can end up in Blocked after transient failures.
- The blocked reconciler scans Blocked issues and moves narrowly-matched cured patrol tickets to Done only when apply mode is enabled.

Configuration lives in `symphony-host.service` / `/home/james/symphony-host.env`:

- `SYMPHONY_BLOCKED_RECONCILER_ENABLED`
  - default: `true`
  - `false` disables the scan entirely.
- `SYMPHONY_BLOCKED_RECONCILER_APPLY`
  - default: `false`
  - `false` logs decisions only; no Plane mutation.
  - `true` transitions matching tickets and posts a reconciler comment.
- `SYMPHONY_BLOCKED_RECONCILER_INTERVAL_MS`
  - default: `1800000` (30 minutes).
  - Controls how often the forever loop scans Blocked tickets. Normal Todo polling still uses `SYMPHONY_POLL_INTERVAL_MS`.
  - The first tick after service start runs the scan immediately; later ticks wait for the interval.

Evidence contract:

- Patrol pass handling for Blocked tickets must post `Patrol pass for ...` comments while leaving the issue in Blocked.
- The reconciler counts distinct pass comments newer than the latest failure comment.
- It does not trust `consecutive_passes=N` as the gate; that value is diagnostic only.
- Tickets with `approval-required` are skipped.
- Comment fetches are paginated and capped per issue to avoid unbounded Plane API reads.

Expected logs:

- `blocked_reconcile_skipped ... reason=no-pass-since-fail`: no current pass evidence since latest failure.
- `blocked_reconcile_would_apply ... target_state=Done`: dry-run found a candidate; review before apply.
- `blocked_reconcile_applied ... target_state=Done`: apply mode moved the ticket.
- `blocked_reconcile_page_limit_reached` or `blocked_reconcile_comment_page_limit_reached`: cap hit; inspect manually before trusting totals.

Safe enable flow:

```bash
# 1. Verify dry-run candidates first.
journalctl -u symphony-host.service --since '30 minutes ago' --no-pager \
  | grep -E 'blocked_reconcile_(would_apply|skipped|page_limit|comment_page_limit)'

# 2. Only if dry-run looks correct, set apply in /home/james/symphony-host.env.
#    Do not print secrets from this file.

# 3. Restart after approval for this live mutation.
sudo systemctl restart symphony-host.service

# 4. Verify startup and next tick.
journalctl -u symphony-host.service --since '2 minutes ago' --no-pager \
  | grep -E 'symphony_started|blocked_reconcile_(would_apply|applied|skipped)|tick_completed'
```

Rollback:

- Set `SYMPHONY_BLOCKED_RECONCILER_APPLY=false` or remove it from `/home/james/symphony-host.env`.
- Restart `symphony-host.service`.
- Reopen any incorrectly moved Plane tickets manually; the reconciler only moves Blocked → Done for the default patrol rule.

## Telegram Notifications

Symphony sends Telegram messages when tickets transition to **Review** or **Blocked** states. Scheduled and released ticket notifications are intentionally disabled to reduce noise.

### Architecture

- `notifier.py` — `TelegramNotifier` class with async (`send`) and sync (`send_sync`) methods
- `scheduler.py` — calls notifier after IN_REVIEW transitions (plan mode, dirty worktree) and BLOCKED transitions (agent crash, timeout, nonzero exit, stale claim)
- `plane_cli.py` — sends notification on `plane review` and `plane blocked` commands (self-contained, no symphony imports)
- Notifications are fire-and-forget — failures log warnings but do not block the scheduler

### Configuration

Environment variables (loaded by `symphony-host.service` from `/home/james/symphony-host.env`):

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot API token |
| `TELEGRAM_CHAT_ID` | No* | Target chat ID (preferred) |
| `TELEGRAM_HOME_CHANNEL` | No* | Fallback chat ID if `TELEGRAM_CHAT_ID` unset |
| `PLANE_FRONTEND_URL` | No | User-facing Plane base URL for issue links |
| `PLANE_DASHBOARD_URL` | No | User-facing Plane dashboard URL |

\* One of `TELEGRAM_CHAT_ID` or `TELEGRAM_HOME_CHANNEL` must be set. Do not print token or chat target values in logs or reports.

When both `TELEGRAM_BOT_TOKEN` and a chat ID are present, notifications are enabled. Startup logs confirm: `telegram_notifications_enabled` or `telegram_notifications_disabled`.

### Message Format

- Review: `📋 <b>IDENTIFIER</b>: Issue Name → <b>Review</b>` (with optional reason, Open issue link, and Dashboard link when configured)
- Blocked: `🚫 <b>IDENTIFIER</b>: Issue Name → <b>Blocked</b>` (with reason from agent output, Open issue link, and Dashboard link when configured)
- Scheduled: no Telegram notification
- Released: no Telegram notification

### Testing

Notifier tests live in `/home/james/symphony/tests/test_notifier.py` and cover config resolution, async/sync sending, failure handling, review/blocked messages, URL links, schedule message formatting, and release message formatting.

## Common Failure Pointers

- Missing env: inspect variable names only; do not print values.
- `401 Unauthorized`: Plane local API expects `X-API-Key`.
- `404 Not Found`: verify project UUID, not slug-like IDs.
- `429 Too Many Requests`: keep polling pagination capped.
- `worktree_dirty`: inspect `/home/james/homelab` before dispatch.
- Missing comments: Plane write paths need trailing slashes.

For non-trivial changes, start with this runbook, `/home/james/plane/AGENTS.md`, and the current `symphony-host.service` unit. The retired OpenCode skill path `/home/james/.config/opencode/skills/symphony/SKILL.md` is no longer present on aidev.
