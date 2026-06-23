# Session Capture: Issue #84 flyout staged controls

- Date: 2026-06-21
- Purpose: Capture the `/grill-me` decision for Issue #84 about home lab infra issue-flyout dropdown behavior.
- Scope: Only durable UI/workflow decisions and verified code facts around Schedule and approval controls were captured.

## Durable Facts

- The flyout `ScheduleChip` currently applies immediately: selecting Yes calls `onSchedule({not_before: "next_window", reason: DEFAULT_SCHEDULE_REASON})`, while selecting No calls `onUnschedule()`. Evidence: `web/frontend/components/IssueFlyout.tsx` (`ScheduleChip`).
- The frontend schedule mutation currently mirrors the backend by optimistically setting `scheduled_for` and `state: "todo"`, so the card moves to the To Do column immediately. Evidence: `web/frontend/components/IssueFlyout.tsx` (`useScheduleIssueMutation`).
- The backend `POST /api/issues/{issue_id}/schedule` appends a `Symphony-Schedule:` comment, sets `scheduled_for`, and forces `state = 'todo'`. Evidence: `web/api/main.py` (`schedule_issue`).
- The live `homelab` binding is `type: infra` but has `approval.enabled: false`. Evidence: `bindings.yml` (`homelab` binding).

## Decisions

- Operator accepted the recommended target behavior: dispatch-affecting issue-flyout controls should be staged and applied only when the operator presses Send with the comment, instead of applying as soon as the dropdown/toggle changes. Evidence: Issue #84 operator reply "Yes" to the staged-controls recommendation in this session.
- The accepted default is to stage Schedule and approval controls that can affect dispatch/requeue behavior, while ordinary metadata fields may continue saving immediately. Evidence: Issue #84 staged-controls recommendation accepted in this session.
- The accepted default is to hide Approval/Approved controls for `homelab` because the binding's approval gate is disabled (`approval.enabled: false`). Evidence: `bindings.yml` plus the accepted staged-controls recommendation.

## Evidence

- `web/frontend/components/IssueFlyout.tsx` — current flyout metadata chips, Schedule chip, immediate schedule mutation, and held-issue comment-mode behavior.
- `web/api/main.py` — `/schedule` endpoint writes the schedule marker and moves issues to `todo`.
- `bindings.yml` — `homelab` infra binding has `approval.enabled: false`.
- `wiki/analyses/adr-0018-patrol-medium-risk-window-scheduling.md` and `wiki/CLAIMS.md` C-0299 — documents the current apply-on-change schedule UI from #098.

## Exclusions

- No secrets, credentials, env files, or private material were read or captured.
- The full issue transcript was not archived; only the durable accepted decision and minimal supporting context were captured.
- No code implementation, service restart, or live Podium mutation was performed.

## Open Questions And Follow-Ups

- Implement the staged-on-Send flyout behavior in a follow-up issue: Schedule=Yes should wait for Send, append the operator comment, and schedule the hold without immediate re-dispatch before Send.
- Decide during implementation whether an empty comment with staged changes should be allowed, or whether Send requires comment text.
- Expose or derive binding approval capability in the frontend so Approval/Approved controls only render when approval is enabled, not merely when `binding_type === "infra"`.
