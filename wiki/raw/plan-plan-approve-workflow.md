# Plan: Symphony Plan/Build/Approve Workflow

## Task Description

Add label-driven plan/approval workflow to Symphony. Three new labels (`plan`, `build`, `approved`) enable a two-phase issue lifecycle: (1) plan-only mode where Symphony researches and creates a plan without implementation, then (2) build mode where Symphony executes an approved plan.

## Objective

When James creates a Todo issue with label `plan`, Symphony claims it, renders a plan-mode prompt (no implementation allowed), runs the agent, and on completion forces the issue to `In Review` with `approval-required` added. James reviews, removes `approval-required`, adds `build`, moves back to `Todo`. Symphony picks it up again in build mode, executes the plan, and completes normally.

## Solution Approach

- Add `PLAN`, `BUILD`, `APPROVED` to `PlaneLabel` enum with corresponding Plane API labels
- Add `add_labels()` to `PlaneAdapter` for label manipulation without replacing existing labels
- Add `_resolve_mode()` helper to `scheduler.py` that maps labels → mode string
- Branch scheduler finalization: plan-mode always goes to In Review + approval-required
- Add `mode` field to `IssueData`, inject mode directive header in rendered prompt
- Add plan-mode and build-mode rules to WORKFLOW.md
- Add `plane label`/`plane unlabel` CLI commands to plane_cli.py

## Relevant Files

### Existing Files to Modify

- `/home/james/homelab/automation/homelab-stack/src/homelab_router/plane_contract.py` — PlaneLabel enum, PlaneContract.label_ids
- `/home/james/homelab/automation/homelab-stack/src/homelab_router/plane_adapter.py` — add_labels() method
- `/home/james/homelab/automation/homelab-stack/src/homelab_router/prompt_renderer.py` — IssueData.mode field, mode directive injection
- `/home/james/homelab/WORKFLOW.md` — plan-mode and build-mode rule sections
- `/home/james/plane/symphony/scheduler.py` — _resolve_mode(), plan-mode finalization branch
- `/home/james/plane/symphony/main.py` — import _resolve_mode, set IssueData.mode
- `/home/james/plane/symphony/plane_cli.py` — LABEL_IDS dict, get() transport, label/unlabel commands

### New Files

- (none — all changes to existing files)

### Test Files

- `/home/james/plane/symphony/tests/test_scheduler.py` — new tests for mode resolution, plan-mode finalization
- `/home/james/homelab/automation/homelab-stack/tests/test_plane_contract.py` — verify new labels and label_ids
- `/home/james/homelab/automation/homelab-stack/tests/test_plane_adapter.py` — verify add_labels()
- `/home/james/plane/symphony/tests/test_plane_cli.py` — new tests for label/unlabel commands

## Implementation Phases

### Phase 1: Foundation — Labels & Contract
Create new labels in Plane API, extend PlaneLabel enum, add label_ids to contract.

### Phase 2: Core — Adapter & Scheduler
Add `add_labels()` to adapter, `_resolve_mode()` and plan-mode branch to scheduler.

### Phase 3: Integration — Prompt & CLI & Workflow
Wire mode through renderer, add label/unlabel CLI, update WORKFLOW.md.

## Codex Audit Findings (Round 1)

3 CRITICAL, 6 WARNING, 3 NOTE. Full findings in `plans/.symphony-plan-approve-workflow.state.yml`.

**CRITICAL fixes integrated into plan:**
1. **Label UUID/name mismatch** — Plane API returns UUIDs in label arrays, not names. `_extract_labels` passes them through unchanged. `_oldest_candidate` line 145 compares `"approval-required"` against UUIDs — this is a **pre-existing bug**. FIX: Add `_label_uuid_to_name()` helper using `label_ids` reverse map; use it in `_extract_labels` and `_resolve_mode`.
2. **Initial repo_dirty gate blocks plan mode** — `run_tick` checks dirty BEFORE candidate selection. FIX: Move dirty check after candidate selection + mode resolution; skip for plan mode.
3. **Plan artifact leaves repo dirty** — Plan-mode agent writes plan file, next tick's dirty check deadlocks. FIX: Plan-mode agent posts plan as Plane comment; no repo writes. Remove "skip repo_dirty" — plan mode must not modify repo.

**WARNING fixes integrated:**
4. **add_labels must GET-merge-PATCH** — Already planned; clarified transport needs.
5. **Prompt renderer mode injection** — Use simple string prepend, no section parser needed. WORKFLOW.md has all modes; renderer prepends `## MODE: {mode}` header.
6. **upsert_issue sends names** — Migrate to send UUIDs via `label_ids` map.
7. **provision_plane.py reconciliation** — Update provisioner for new labels.
8. **Transport get() protocol** — Update all transport implementations.

## Step by Step Tasks

### 1. Create Labels in Plane API [sequential]
- [ ] [1.1] Create `plan` label in Plane automations project via POST to labels endpoint, capture UUID
- [ ] [1.2] Create `build` label in Plane automations project, capture UUID
- [ ] [1.3] Create `approved` label in Plane automations project, capture UUID
- [ ] [1.4] Verify all 7 labels exist via GET labels endpoint

### 2. Extend PlaneContract (plane_contract.py) [parallel-safe]
- [ ] [2.1] Add `PLAN = "plan"`, `BUILD = "build"`, `APPROVED = "approved"` to PlaneLabel enum
- [ ] [2.2] Add PLAN, BUILD, APPROVED to PlaneContract.labels default tuple
- [ ] [2.3] Add `label_ids: dict[str, str]` field to PlaneContract (mirrors state_ids pattern)
- [ ] [2.4] Add label_ids to DEFAULT_CONTRACT with all 7 label UUIDs (4 existing + 3 new)
- [ ] [2.5] Add `label_name_for_uuid(uuid)` classmethod to PlaneContract — reverse lookup from label_ids
- [ ] [2.6] Verify contract shape validation still passes

### 3. Fix Pre-Existing Label UUID Bug (plane_poller.py) [CRITICAL]
- [ ] [3.1] Add `_label_uuid_to_name(labels, label_ids)` helper to plane_poller.py — maps UUIDs to names
- [ ] [3.2] Update `_extract_labels` to use UUID→name mapping when `label_ids` is provided
- [ ] [3.3] Thread `label_ids` through `fetch_todo_issues` signature (from adapter.config.contract)
- [ ] [3.4] Add regression test: issue with UUID-only labels correctly filtered by approval-required name
- [ ] [3.5] Verify existing tests still pass after label resolution change

### 4. Add add_labels() to PlaneAdapter (plane_adapter.py) [parallel-safe]
- [ ] [4.1] Add `add_labels(issue_id, label_names)` method to PlaneAdapter
- [ ] [4.2] Method: GET current issue → extract label UUIDs → union with new UUIDs (from label_ids) → PATCH
- [ ] [4.3] Add `get_issue(issue_id)` helper to PlaneAdapter for fetching single issue
- [ ] [4.4] Migrate `upsert_issue` to send label UUIDs (not names) via label_ids map
- [ ] [4.5] Update transport protocol: add `get()` to all implementations (UrllibTransport, InMemoryTransport, FakeTransport)

### 5. Add _resolve_mode() and Plan Branch to Scheduler (scheduler.py)
- [ ] [5.1] Add `_resolve_mode(labels: Sequence[str], label_ids: dict[str, str]) -> str` — maps label UUIDs → names → mode
- [ ] [5.2] Priority: plan > build > execute (if plan UUID present → plan; elif build UUID → build; else execute)
- [ ] [5.3] In run_tick(): move repo_dirty check AFTER candidate selection and mode resolution
- [ ] [5.4] Skip repo_dirty check only for plan mode (plan must not write to repo)
- [ ] [5.5] In finalization: if mode == "plan", transition to In Review + add approval-required label
- [ ] [5.6] Plan-mode comment: "Symphony completed plan. Awaiting approval." + agent report
- [ ] [5.7] Plan-mode agent should NOT modify repo — plan posted as Plane comment only
- [ ] [5.8] Build and execute modes follow existing done/review flow (no changes)

### 6. Wire Mode Through Prompt Renderer (prompt_renderer.py + main.py)
- [ ] [6.1] Add `mode: str = "execute"` field to IssueData dataclass
- [ ] [6.2] In render_prompt(), prepend `## MODE: {mode.upper()}\n\n` header before WORKFLOW content
- [ ] [6.3] In main.py, import _resolve_mode from scheduler
- [ ] [6.4] In _render_candidate_prompt(), set IssueData.mode = _resolve_mode(issue.labels, label_ids)
- [ ] [6.5] Translate label UUIDs → names in prompt's labels field (for human-readable display)

### 7. Update WORKFLOW.md
- [ ] [7.1] Add `## Plan Mode` section: no implementation, explore only, post findings as comment, do NOT modify repo
- [ ] [7.2] Add `## Build Mode` section: read plan from issue history/comments, execute plan, normal rules apply

### 8. Add label/unlabel CLI Commands (plane_cli.py)
- [ ] [8.1] Add `LABEL_IDS` dict mapping label names to UUIDs (mirrors STATE_IDS pattern)
- [ ] [8.2] Add `get()` to UrllibTransport (sync urllib GET for single issue fetch)
- [ ] [8.3] Add `label <name>` command: GET current labels, append UUID, PATCH
- [ ] [8.4] Add `unlabel <name>` command: GET current labels, remove UUID, PATCH
- [ ] [8.5] Update usage string to include label/unlabel

### 9. Update Provisioner (provision_plane.py) [parallel-safe]
- [ ] [9.1] Add plan, build, approved to provisioner's label creation list with distinct colors
- [ ] [9.2] Verify provisioner outputs stable UUIDs that match DEFAULT_CONTRACT.label_ids

### 10. Write Tests
- [ ] [10.1] Test _resolve_mode with UUID inputs returns "plan" when plan UUID present
- [ ] [10.2] Test _resolve_mode returns "build" when build UUID present (no plan)
- [ ] [10.3] Test _resolve_mode returns "execute" with no mode labels
- [ ] [10.4] Test plan-mode issue transitions to In Review + approval-required
- [ ] [10.5] Test plan-mode issue does NOT skip repo_dirty if repo was already dirty before tick
- [ ] [10.6] Test build-mode issue follows normal done/review flow
- [ ] [10.7] Test plane label command patches labels correctly (GET-merge-PATCH)
- [ ] [10.8] Test plane unlabel command removes label correctly
- [ ] [10.9] Test _extract_labels with UUID strings maps to names correctly
- [ ] [10.10] Test regression: approval-required filter works with UUID-only labels
- [ ] [10.11] Test add_labels preserves existing labels (no overwrite)
- [ ] [10.12] Test prompt renderer prepends MODE header
- [ ] [10.13] Test label UUID→name translation in prompt labels field

### 11. Validate & Run Tests [sequential]
- [ ] [11.1] Run `python3 -m pytest` in /home/james/plane/symphony — all tests pass
- [ ] [11.2] Run `uv run pytest` in /home/james/homelab/automation/homelab-stack — all tests pass
- [ ] [11.3] Verify Plane has all 7 labels via API
- [ ] [11.4] Ask James before restarting Symphony container

## Tests

### T.1. Label UUID Resolution (addresses Codex Critical #1)
- [ ] [T.1.1] _extract_labels(["uuid-of-approval-required"]) → ("approval-required",) with label_ids provided
- [ ] [T.1.2] _extract_labels(["unknown-uuid"]) → ("unknown-uuid",) — passthrough for unknown UUIDs
- [ ] [T.1.3] fetch_todo_issues skips issues with approval-required UUID in labels
- [ ] [T.1.4] _resolve_mode(["plan-uuid"], label_ids) == "plan"

### T.2. Mode Resolution
- [ ] [T.2.1] _resolve_mode with plan UUID → "plan"
- [ ] [T.2.2] _resolve_mode with plan+build UUIDs → "plan" (plan wins)
- [ ] [T.2.3] _resolve_mode with build UUID → "build"
- [ ] [T.2.4] _resolve_mode with approved UUID → "execute" (approved is metadata only)
- [ ] [T.2.5] _resolve_mode with empty labels → "execute"

### T.3. Plan-Mode Scheduler
- [ ] [T.3.1] Plan issue → In Review state, approval-required label added
- [ ] [T.3.2] Plan issue comment contains "Awaiting approval" text
- [ ] [T.3.3] Plan issue with dirty repo from PREVIOUS tick still dispatches (dirty check after mode resolution)
- [ ] [T.3.4] Plan issue receives plan-mode prompt (mode field set)
- [ ] [T.3.5] Plan issue agent output posted as comment, repo NOT modified

### T.4. Build-Mode Scheduler
- [ ] [T.4.1] Build issue with clean repo → Done
- [ ] [T.4.2] Build issue with dirty repo → In Review (normal flow)

### T.5. Label CLI
- [ ] [T.5.1] `plane label plan` appends plan UUID to issue labels
- [ ] [T.5.2] `plane unlabel plan` removes plan UUID from issue labels
- [ ] [T.5.3] Unknown label name raises PlaneCliError
- [ ] [T.5.4] `plane label` preserves existing labels (no overwrite)

## Progress

**Codex Audit:** Round 1 complete (3 CRITICAL, 6 WARNING, 3 NOTE). Plan revised.

**Phase Status:**
- Build: `pending`
- Test: `pending`

**Task Counts:**
- Implementation: `0/46` tasks complete
- Tests: `0/19` tests passing

**Last Updated:** `Codex R1 revised`

## Acceptance Criteria

1. Plane automations project has `plan`, `build`, `approved` labels
2. `PlaneLabel` enum includes PLAN, BUILD, APPROVED
3. `_resolve_mode()` correctly prioritizes plan > build > execute
4. Plan-mode issues always transition to In Review with approval-required
5. Build-mode issues follow normal done/review flow
6. `plane label` and `plane unlabel` CLI commands work
7. Agent prompt includes mode directive header
8. WORKFLOW.md has plan-mode and build-mode sections
9. All existing tests continue to pass
10. New tests cover all acceptance criteria

## Testing Promise

All unit tests in `plane/symphony/tests/` and `homelab/automation/homelab-stack/tests/` pass with zero failures.

## Validation Commands

```bash
# Symphony tests
cd /home/james/plane/symphony && python3 -m pytest -v

# Homelab-stack tests
cd /home/james/homelab/automation/homelab-stack && uv run pytest -v

# Verify Plane labels exist
source /home/james/homelab/.env && curl -s -H "X-API-Key: $PLANE_API_KEY" \
  "http://127.0.0.1:8000/api/v1/workspaces/homelab/projects/cff68c17-bff6-452f-89b3-9b570613cfaa/labels/" \
  | python3 -c "import json,sys; [print(l['name']) for l in json.load(sys.stdin)['results']]"
```

## Notes

- Label UUIDs will be captured from Plane API after creation and hardcoded in DEFAULT_CONTRACT
- `approved` label is informational metadata — no behavior change in scheduler
- Only `plan` mode adds `approval-required`; `build` and `execute` complete normally
- **CRITICAL FIX:** Pre-existing bug — Plane returns UUIDs in label arrays, but poller compared names. Fixed by adding UUID→name mapping via label_ids.
- **CRITICAL FIX:** repo_dirty check moved after mode resolution; plan mode skips it (agent must not modify repo in plan mode)
- **CRITICAL FIX:** Plan-mode agent posts findings as Plane comment only; no plan file written to repo (avoids dirty-worktree deadlock)
- `_extract_labels` now resolves UUIDs → names using label_ids reverse map
- `_resolve_mode` accepts UUID inputs, resolves internally
- Prompt renderer prepends simple MODE header (no section parser needed)
- `add_labels` uses GET-merge-PATCH to preserve existing labels
- FakeTransport needs `labels` tracking and GET support for tests
