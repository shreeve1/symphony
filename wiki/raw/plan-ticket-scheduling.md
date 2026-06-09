# Plan: Symphony Ticket Scheduling

## Task Description

Add one-shot, ticket-native scheduling to Symphony so James or a Symphony agent can defer an existing Plane ticket until a safe maintenance window. Agent/CLI scheduling uses a dedicated `scheduled` Plane label plus append-only structured comments. James can also add only the `scheduled` label; label-only scheduled tickets default to the next 12am-6am America/Los_Angeles maintenance window. A scheduled ticket remains `Todo + scheduled` until its `not_before` time, then Symphony releases exactly one due ticket per tick, removes the `scheduled` label, writes an audit comment, and dispatches it through the normal claim/run/finalize flow.

## Objective

When this plan is complete, Symphony can safely schedule, unschedule, hold, release, and execute existing Plane tickets using explicit ISO 8601 offset timestamps when a schedule comment exists, a deterministic 12am-6am PT maintenance window when James applies only the `scheduled` label, required audit reasons, deterministic queue ordering, and test-covered failure behavior for malformed or inconsistent schedule state.

## Problem Statement

Today Symphony polls Todo issues and dispatches eligible work immediately. That is unsafe or inconvenient for agent-recommended maintenance tasks that should happen during a chosen window, such as updates, reboots, storage operations, or other potentially disruptive homelab work. James needs agents to be able to recommend and schedule later execution on the same ticket without creating a separate queue system or relying on ambiguous natural-language comments.

## Solution Approach

Implement a minimal scheduling layer inside the existing Plane-backed Symphony flow:

- Add a `scheduled` Plane label to the static Plane contract and CLI label map after the label exists in Plane.
- Add schedule parsing helpers for append-only `Symphony-Schedule:` and `Symphony-Schedule-Cancelled:` comment events.
- Add `plane schedule` and `plane unschedule` helper commands for dispatched agents.
- Modify polling/scheduler logic so future scheduled tickets are held, label-only scheduled tickets use the next 12am-6am PT maintenance window, malformed scheduled tickets fail loud, due scheduled tickets outrank ordinary Todo, and only one ticket is released/dispatched per tick.
- Add prompt schedule context when a due scheduled ticket executes.
- Keep scheduling one-shot only; recurring work remains in Windmill/cron/patrol systems.

## Relevant Files

Use these files to complete the task:

### Existing Files to Modify

- `/home/james/homelab/automation/homelab-stack/src/homelab_router/plane_contract.py` — add `scheduled` to `PlaneLabel`, `DEFAULT_CONTRACT.labels`, and `DEFAULT_CONTRACT.label_ids` after label UUID is known.
- `/home/james/homelab/automation/homelab-stack/src/homelab_router/plane_adapter.py` — reuse or extend label/comment/state helpers for release, repair, block, and schedule mutations.
- `/home/james/homelab/automation/homelab-stack/src/homelab_router/prompt_renderer.py` — add optional schedule context to `IssueData` and render a `## Schedule Context` block.
- `/home/james/plane/symphony/plane_poller.py` — skip held future scheduled tickets during ordinary polling and avoid schedule starvation.
- `/home/james/plane/symphony/scheduler.py` — parse schedule events, apply the label-only 12am-6am PT default window when no schedule comment exists, release due scheduled tickets before ordinary polling, handle malformed/cancelled schedule states, inject schedule context, and recognize agent-created schedules after agent exit.
- `/home/james/plane/symphony/plane_cli.py` — add `plane schedule` and `plane unschedule` commands with validation, comments, label mutations, and Todo transitions.
- `/home/james/plane/symphony/scripts/sync_plane_ids.py` — extend generated CLI ID sync so schedule commands can patch Todo and include the new provisioned label UUID.
- `/home/james/plane/symphony/main.py` — pass schedule context from scheduler/candidate data into prompt rendering if needed.
- `/home/james/plane/symphony/notifier.py` — reuse existing notifier interface for schedule and release notifications if no change is needed; extend only if current shape cannot express scheduled/released messages.

### New Files

- `/home/james/plane/symphony/schedule.py` — schedule event parser, serializer, validation helpers, and value objects used by scheduler and CLI.

### Test Files

- `/home/james/plane/symphony/tests/test_scheduler.py` — scheduler release/hold/block/repair/post-agent scheduling behavior.
- `/home/james/plane/symphony/tests/test_plane_poller.py` — scheduled-label polling exclusions and non-starvation behavior.
- `/home/james/plane/symphony/tests/test_plane_cli.py` — `schedule` and `unschedule` command validation and Plane mutations.
- `/home/james/plane/symphony/tests/test_main.py` — prompt rendering handoff for schedule context, if main wiring changes.
- `/home/james/plane/symphony/tests/test_notifier.py` — schedule/release notification formatting, if notifier changes.
- `/home/james/homelab/automation/homelab-stack/tests/test_plane_contract.py` — static `scheduled` label UUID contract coverage.
- `/home/james/homelab/automation/homelab-stack/tests/test_prompt_renderer.py` — schedule context block rendering and escaping.
- `/home/james/homelab/automation/homelab-stack/tests/test_plane_adapter.py` — adapter label/comment/state helper coverage if adapter changes.

## Implementation Phases

### Phase 1: Foundation

Create or discover the `scheduled` Plane label UUID, extend the static contract, and add schedule parsing/serialization primitives without changing dispatch behavior.

### Phase 2: Core Implementation

Add CLI schedule/unschedule commands and scheduler release/hold/block/repair behavior, including post-agent recognition that a Running ticket was rescheduled to `Todo + scheduled`.

### Phase 3: Integration & Polish

Add prompt schedule context, schedule/release notifications, tests across Symphony and homelab integration, and deterministic validation commands.

## Step by Step Tasks

IMPORTANT: Execute every step in order when running manually. Build will parallelize independent groups automatically.

### 1. Provision Scheduled Label [sequential]
- [ ] [1.1] Create or locate the `scheduled` label in the Plane automations project and capture its UUID.
- [ ] [1.2] Verify the label belongs to project `cff68c17-bff6-452f-89b3-9b570613cfaa` and is named exactly `scheduled`.
- [ ] [1.3] Record the UUID in the implementation notes before editing static contract files.

### 2. Extend Static Plane Contract
- [ ] [2.1] Add `SCHEDULED = "scheduled"` to `PlaneLabel` in `plane_contract.py`.
- [ ] [2.2] Add `PlaneLabel.SCHEDULED` to `DEFAULT_CONTRACT.labels`.
- [ ] [2.3] Add `PlaneLabel.SCHEDULED` to `DEFAULT_CONTRACT.provisioned_labels`; `validate_shape()` rejects `label_ids` entries for non-provisioned labels.
- [ ] [2.4] Add the captured `scheduled` UUID to `DEFAULT_CONTRACT.label_ids`.
- [ ] [2.5] Extend `scripts/sync_plane_ids.py` so `STATE_IDS` includes the Todo UUID under a schedule-specific key such as `todo`, while preserving existing terminal-state verbs.
- [ ] [2.6] Regenerate `plane_cli.py` with `python3 scripts/sync_plane_ids.py` so `LABEL_IDS` includes `scheduled` and `STATE_IDS` includes Todo.
- [ ] [2.7] Update contract and CLI drift tests to assert `scheduled` is present in `labels`, `provisioned_labels`, `label_ids`, and generated `LABEL_IDS`, and that generated CLI state IDs include Todo.

### 3. Add Schedule Domain Helpers
- [ ] [3.1] Create `schedule.py` with a small immutable schedule record containing `not_before`, optional advisory `not_after`, required `reason`, source event type, raw comment, and parsed creation time if available.
- [ ] [3.2] Implement parser support for single-line key-value comments: `Symphony-Schedule: not_before=<iso> not_after=<iso> reason="..."`.
- [ ] [3.3] Implement cancellation parser support for `Symphony-Schedule-Cancelled: reason="..."`.
- [ ] [3.4] Normalize Plane `comment_html` before parsing: strip simple HTML wrappers, decode entities, and preserve quoted values so CLI-authored comments round-trip through Plane.
- [ ] [3.5] Validate that `not_before` uses ISO 8601 with an explicit UTC offset or `Z`; reject naive datetimes and natural language.
- [ ] [3.6] Validate that `reason` is required and non-empty for both schedule and cancellation events.
- [ ] [3.7] Treat `not_after` as advisory only; parse it if present, reject malformed values, and reject `not_after < not_before` as invalid schedule state.
- [ ] [3.8] Implement latest-event-wins selection across schedule and cancellation comments sorted by comment creation time, with a deterministic secondary tie-breaker using Plane comment ID or API order.
- [ ] [3.9] Add unit tests for valid schedule, valid cancellation, missing reason, naive timestamp, malformed key-value syntax, HTML/entity round-trip, `not_after < not_before`, identical `created_at` tie-breaks, latest schedule wins, latest cancellation wins, and reschedule after cancellation.

### 4. Add Agent CLI Schedule Commands
- [ ] [4.1] Add `plane schedule --not-before <iso> --reason <text> [--not-after <iso>]` to `plane_cli.py`.
- [ ] [4.2] Make `plane schedule` reject target override flags just like existing state/comment/label commands.
- [ ] [4.3] Make `plane schedule` validate arguments locally before any Plane mutation.
- [ ] [4.4] Make `plane schedule` add the structured `Symphony-Schedule:` comment, add the `scheduled` label, and transition the current issue to Todo.
- [ ] [4.5] Add `plane unschedule --reason <text>` that adds `Symphony-Schedule-Cancelled: reason="..."`, removes the `scheduled` label, and leaves or transitions the issue to Todo.
- [ ] [4.6] Ensure CLI commands preserve existing labels via GET-merge-PATCH and never overwrite unrelated labels.
- [ ] [4.7] Make schedule and unschedule fail fast if generated `STATE_IDS` lacks the Todo UUID or `LABEL_IDS` lacks the `scheduled` UUID.
- [ ] [4.8] Add CLI tests for success paths, missing required reason, invalid timestamps, target override rejection, existing-label preservation, Todo PATCH bodies, missing generated IDs, and Plane error propagation.

### 5. Teach Polling To Ignore Held Future Schedules
- [ ] [5.1] Update `fetch_todo_issues()` or its candidate filtering so `Todo + scheduled` tickets are not returned through ordinary polling before release.
- [ ] [5.2] Prefer a server-side label exclusion if Plane supports it; otherwise continue paginating past scheduled-only pages within an explicit ordinary-poll page budget so future scheduled tickets cannot consume the whole `MAX_PAGES_PER_TICK` window.
- [ ] [5.3] Preserve existing exclusions for `approval-required`.
- [ ] [5.4] Add poller tests proving future scheduled tickets are skipped while ordinary Todo candidates on later pages remain eligible, including a case where early pages contain only scheduled tickets.

### 6. Add Scheduled Release Step To Scheduler [sequential]
- [ ] [6.1] Add a pre-poll scheduler step that fetches Todo issues with the `scheduled` label independently of ordinary polling.
- [ ] [6.2] Define a separate scheduled-release page budget and server-side label filter for the pre-poll step so due tickets hidden behind future scheduled tickets are still considered.
- [ ] [6.3] For each scheduled candidate, fetch comments and determine the latest schedule event.
- [ ] [6.4] If the latest event is a valid future schedule, hold it and continue searching without dispatching.
- [ ] [6.5] If the latest event is a valid due or past schedule, select it as the release candidate.
- [ ] [6.6] If multiple schedules are due or late, sort by earliest `not_before`, then by ticket `created_at`, then by issue ID for deterministic ties.
- [ ] [6.7] Release at most one scheduled ticket per tick.
- [ ] [6.8] Immediately before release mutation, refetch comments and labels; abort/repair if a newer cancellation or malformed event now controls.
- [ ] [6.9] Write the release audit comment before removing the `scheduled` label; if audit comment fails, leave the ticket scheduled and do not run it.
- [ ] [6.10] Remove the `scheduled` label only after the audit comment succeeds, then transition to Running through the normal claim path.
- [ ] [6.11] If label removal, claim, or later release mutation fails after partial progress, re-add `scheduled` when safe or block with a clear partial-release failure comment; do not leave an unaudited ordinary Todo that can run next tick.
- [ ] [6.12] Add release tests for due scheduled priority over ordinary Todo, one-per-tick behavior, release order, due ticket beyond future scheduled backlog, cancellation race, audit-before-unlabel ordering, partial-failure recovery, and late advisory audit content.

### 7. Handle Broken And Cancelled Schedule States
- [ ] [7.1] If `Todo + scheduled` has no latest valid `Symphony-Schedule:` or cancellation event, use the label-only 12am-6am PT maintenance-window fallback instead of blocking.
- [ ] [7.2] If the latest `Symphony-Schedule:` is malformed, block the ticket with a parse-error comment and do not fall back to older valid schedules.
- [ ] [7.3] If the latest event is `Symphony-Schedule-Cancelled:` and the `scheduled` label remains, auto-remove the stale label, add a short repair audit comment, and leave the issue Todo.
- [ ] [7.4] Add tests for missing comment, malformed latest schedule, cancellation repair, and comment-only schedule ignored when the label is absent.

### 8. Recognize Agent-Created Schedules After Dispatch
- [ ] [8.1] After an agent exits successfully, refetch the issue before `repo_dirty()` and `auto_commit()` logic, not merely before final terminal-state handling.
- [ ] [8.2] If the agent changed the issue to `Todo + scheduled` with a valid schedule event newer than the claim/agent start time, return a new reason such as `agent-scheduled` and do not transition Done.
- [ ] [8.3] Add an append-only `Symphony scheduled follow-up:` audit comment that includes sanitized stdout/stderr summaries or explicitly states there was no output, so agent reasoning is not silently lost.
- [ ] [8.4] If the agent attempted to schedule but produced malformed schedule state, block with the same parse/missing-schedule handling used for manual schedules.
- [ ] [8.5] Add tests proving a clean-exit agent that runs `plane schedule` is not marked Done, does not call `auto_commit` even with a dirty repo, ignores stale pre-claim schedules, and blocks malformed agent schedule state.

### 9. Add Prompt Schedule Context
- [ ] [9.1] Extend `IssueData` in `prompt_renderer.py` with optional schedule context fields.
- [ ] [9.2] Render a `## Schedule Context` block when a due scheduled ticket is released for execution.
- [ ] [9.3] Include `not_before`, optional advisory `not_after`, required `reason`, source if known, and `late=true|false`.
- [ ] [9.4] Escape schedule context fields consistently with existing issue/comment escaping.
- [ ] [9.5] Wire scheduler/main prompt creation so released scheduled tickets receive schedule context and ordinary tickets do not.
- [ ] [9.6] Add prompt renderer tests for context presence, absence, late flag, and escaping.

### 10. Add Schedule And Release Notifications
- [ ] [10.1] On successful `plane schedule`, send a schedule notification if Telegram configuration is present.
- [ ] [10.2] On successful scheduler release, send a release notification including `late=true` when execution starts after advisory `not_after`.
- [ ] [10.3] Notify on malformed schedule blocking and partial-release blocking because those are schedule-control-plane failures that require attention.
- [ ] [10.4] Do not notify on every idle poll while a scheduled ticket is waiting.
- [ ] [10.5] Add notifier or scheduler tests for schedule notification, release notification, late flag, malformed/partial-failure notification, and no idle spam.

### 11. Validate And Document Operator Constraints [sequential]
- [ ] [11.1] Update user-facing command usage in `plane_cli.py` so agents see `schedule` and `unschedule` syntax.
- [ ] [11.2] Add notes in the plan or nearest Symphony runbook that recurring schedules remain out of scope and belong in Windmill/cron/patrol.
- [ ] [11.3] Confirm no code path performs live Plane label creation automatically; label provisioning remains an explicit prerequisite.
- [ ] [11.4] Run the validation commands from this plan.

## Testing Strategy

Use focused pytest coverage, not live Plane/Windmill/pi mutations. Most behavior can be covered with existing fake transports and scheduler fake adapters. Tests should prove the safety properties: never execute before `not_before`, malformed schedules block, cancellation repairs stale labels, due scheduled tickets outrank ordinary Todo, and an agent-created schedule is not overwritten by scheduler clean-exit finalization.

## Tests

### T.1. Schedule Parser
- [ ] [T.1.1] Parse valid `Symphony-Schedule:` with required `not_before` and `reason`.
- [ ] [T.1.2] Parse valid schedule with advisory `not_after`.
- [ ] [T.1.3] Reject schedule with missing reason.
- [ ] [T.1.4] Reject schedule with naive or natural-language timestamp.
- [ ] [T.1.5] Reject advisory `not_after` that is earlier than `not_before`.
- [ ] [T.1.6] Normalize and parse Plane-returned `comment_html` with wrappers, entities, quotes, `<`, and `>`.
- [ ] [T.1.7] Reject malformed latest schedule rather than falling back to older valid schedule.
- [ ] [T.1.8] Select latest event across schedule and cancellation comments with deterministic ties.

### T.2. CLI Commands
- [ ] [T.2.1] `plane schedule --not-before ... --reason ...` posts schedule comment, adds `scheduled`, and patches state to Todo.
- [ ] [T.2.2] `plane schedule` rejects missing reason, invalid timestamp, and target override flags before mutation.
- [ ] [T.2.3] `plane unschedule --reason ...` posts cancellation comment, removes `scheduled`, and leaves Todo.
- [ ] [T.2.4] Schedule and unschedule preserve unrelated labels.
- [ ] [T.2.5] Generated CLI `STATE_IDS` includes Todo and generated `LABEL_IDS` includes `scheduled`; missing generated IDs fail fast.

### T.3. Polling And Release
- [ ] [T.3.1] Future scheduled tickets are held and ordinary Todo tickets still dispatch.
- [ ] [T.3.2] Due scheduled ticket releases before ordinary Todo.
- [ ] [T.3.3] Only one due scheduled ticket releases per tick.
- [ ] [T.3.4] Multiple due scheduled tickets order by earliest `not_before`, then `created_at`.
- [ ] [T.3.5] Due scheduled tickets beyond future scheduled backlog are still found within the scheduled-release budget.
- [ ] [T.3.6] Release writes audit before removing `scheduled`, then claims Running.
- [ ] [T.3.7] Release aborts or repairs safely on audit, unlabel, claim, and cancellation-race failures.
- [ ] [T.3.8] Late release includes advisory late audit content and notification flag.

### T.4. Broken State Handling
- [ ] [T.4.1] `Todo + scheduled` without schedule event waits outside the 12am-6am PT maintenance window and releases during it.
- [ ] [T.4.2] Malformed latest schedule blocks with parse-error comment.
- [ ] [T.4.3] Latest cancellation with stale `scheduled` label auto-removes label and leaves Todo.
- [ ] [T.4.4] Schedule comment without `scheduled` label does not activate scheduling.

### T.5. Agent Finalization
- [ ] [T.5.1] Clean-exit agent that schedules current issue returns `agent-scheduled` and is not transitioned Done.
- [ ] [T.5.2] Agent-created malformed schedule blocks instead of completing Done.
- [ ] [T.5.3] Existing agent terminal states Done/In Review/Blocked continue to take precedence.
- [ ] [T.5.4] Dirty repo plus valid agent-created schedule does not invoke `auto_commit`.
- [ ] [T.5.5] Stale pre-claim schedule comments do not count as agent-created schedules.

### T.6. Prompt And Notifications
- [ ] [T.6.1] Released scheduled ticket prompt includes `## Schedule Context` with timing, reason, source, and late flag.
- [ ] [T.6.2] Ordinary Todo prompt has no schedule context block.
- [ ] [T.6.3] Schedule notification fires once when scheduling succeeds.
- [ ] [T.6.4] Release notification fires once when release succeeds and includes `late=true` when applicable.
- [ ] [T.6.5] Malformed schedules and partial release failures notify once without idle-poll spam.

## Progress

**Phase Status:**
- Build: `pending`
- Test: `pending`

**Task Counts:**
- Implementation: `0/67` tasks complete
- Tests: `0/35` tests passing

**Last Updated:** `2026-05-08 Codex R1 revised after FAIL audit`

## Acceptance Criteria

1. `scheduled` Plane label exists in the static contract and CLI label map with the correct UUID.
2. `scheduled` is included in `labels`, `provisioned_labels`, `label_ids`, generated `LABEL_IDS`, and matching contract/CLI drift tests.
3. Generated CLI `STATE_IDS` includes a Todo UUID that schedule/unschedule use for Todo transitions.
4. `plane schedule` requires `--not-before` and `--reason`, accepts optional advisory `--not-after`, validates ISO offset timestamps, adds schedule comment, adds `scheduled`, and transitions current issue to Todo.
5. `plane unschedule` requires `--reason`, adds cancellation comment, removes `scheduled`, and leaves or transitions the current issue to Todo.
6. Symphony never executes a scheduled ticket before `not_before`.
7. Symphony rejects malformed timestamps, malformed HTML/comment encodings, and `not_after < not_before` as invalid schedule state.
8. Symphony runs late schedules anyway, with audit and notification indicating lateness when after advisory `not_after`.
9. Due scheduled tickets outrank ordinary Todo tickets, but Symphony releases no more than one scheduled ticket per tick.
10. Future scheduled tickets do not starve ordinary Todo polling or hide due scheduled tickets behind page limits.
11. Latest schedule-related event wins across schedule and cancellation comments with deterministic tie-breaking.
12. Missing controlling schedule comments fall back to the label-only 12am-6am PT maintenance window, while malformed controlling schedule state blocks loudly and does not execute.
13. Latest cancellation with stale `scheduled` label is auto-repaired by removing the label and adding audit context.
14. Release writes an audit comment before unlabeling; partial failures cannot leave an unaudited ordinary Todo that can run next tick.
15. Clean-exit agents that schedule their current ticket are not overwritten by scheduler Done finalization or auto-committed before schedule detection.
16. Agent-created schedule detection requires a controlling schedule comment newer than the claim/agent start time.
17. Released scheduled tickets receive prompt schedule context; ordinary tickets do not.
18. Schedule, release, malformed-schedule, and partial-release notifications fire once per event and never on idle polling.
19. All new behavior is covered by tests without live Plane, Windmill, systemd, or pi mutations.

## Testing Promise

All Symphony tests in `/home/james/plane/symphony/tests/` and relevant homelab automation tests in `/home/james/homelab/automation/homelab-stack/tests/` pass with zero failures, proving scheduling cannot execute before `not_before`, label-only scheduled tickets respect the 12am-6am PT maintenance window, malformed schedules fail loud, and agent-created schedules are not marked Done.

## Validation Commands

Execute these commands to validate the task is complete:

- `python3 -m pytest` from `/home/james/plane/symphony` - Run the full Symphony test suite.
- `python3 -m py_compile *.py` from `/home/james/plane/symphony` - Compile top-level Symphony modules.
- `uv run pytest tests/test_plane_contract.py tests/test_prompt_renderer.py tests/test_plane_adapter.py` from `/home/james/homelab/automation/homelab-stack` - Run impacted homelab automation tests.
- `git diff --check` from `/home/james/plane/symphony` - Verify Symphony patch whitespace.
- `git diff --check` from `/home/james/homelab` - Verify homelab integration patch whitespace.

## Notes

- This plan intentionally does not create Plane labels automatically. Label creation/discovery is a live Plane/admin prerequisite and should be approved separately.
- Recurring schedules are out of scope. Use Windmill, cron, or patrol systems for recurring work.
- `not_after` is advisory only. The hard invariant is: never execute before `not_before`.
- Scheduling is allowed on any Symphony ticket; no domain-label gate is required.
- Schedule comments alone do not activate scheduling. Manual label-only schedules require the `scheduled` label and use the next 12am-6am PT maintenance window when no valid schedule comment exists.
- The implementation should avoid live service restarts or smoke requeues unless James explicitly approves them.
